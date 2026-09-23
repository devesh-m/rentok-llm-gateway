import pytest
from app.config import settings


@pytest.mark.asyncio
async def test_health_check(client):
    """Verify service health endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "service" in data


@pytest.mark.asyncio
async def test_auth_invalid_key(client):
    """Verify that an invalid or unauthenticated virtual key returns 401."""
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": "Hello"}],
    }
    response = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer gw-live-invalid-key"},
        json=payload,
    )
    assert response.status_code == 401
    assert "Invalid virtual API key" in response.json()["detail"]["error"]["message"]


@pytest.mark.asyncio
async def test_budget_enforcement_clean_429(client):
    """
    CRITICAL REQUIREMENT #3:
    Verify that an over-budget key is cleanly rejected with HTTP 429 and does not pass through.
    """
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": "This request should be blocked."}],
    }
    response = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer gw-live-exhausted"},
        json=payload,
    )
    assert response.status_code == 429
    data = response.json()
    assert data["detail"]["error"]["type"] == "budget_exceeded"
    assert "Budget limit exceeded" in data["detail"]["error"]["message"]


@pytest.mark.asyncio
async def test_chat_proxy_success_and_spend_logging(client):
    """
    CRITICAL REQUIREMENTS #1 & #4:
    Proxy a chat call, verify response structure, and verify spend is persisted.
    """
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": "Hello LLM Gateway!"}],
    }
    response = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer gw-live-test"},
        json=payload,
    )
    assert response.status_code == 200
    data = response.json()
    assert "choices" in data
    assert len(data["choices"]) > 0
    assert data["choices"][0]["message"]["content"] is not None
    assert data["usage"]["total_tokens"] > 0
    assert "X-Provider" in response.headers

    # Query usage to verify spend was logged
    usage_resp = await client.get("/v1/admin/usage?key=gw-live-test")
    assert usage_resp.status_code == 200
    usage_data = usage_resp.json()
    assert usage_data["current_spend_usd"] > 0.0
    assert usage_data["total_requests"] == 1
    assert len(usage_data["recent_logs"]) == 1


@pytest.mark.asyncio
async def test_caching_and_cost_savings(client):
    """
    STRETCH GOAL:
    Verify that repeating an identical prompt results in a cache HIT and tracks savings.
    """
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": "Explain gravity in one sentence."}],
    }
    headers = {"Authorization": "Bearer gw-live-test"}

    # First request: Cache MISS
    resp1 = await client.post("/v1/chat/completions", headers=headers, json=payload)
    assert resp1.status_code == 200
    assert resp1.headers["X-Cache"] == "MISS"

    # Second request: Cache HIT
    resp2 = await client.post("/v1/chat/completions", headers=headers, json=payload)
    assert resp2.status_code == 200
    assert resp2.headers["X-Cache"] == "HIT"
    assert resp2.headers["X-Provider"] == "cache"

    # Verify cache analytics reflect the hit and cost saved
    stats_resp = await client.get("/v1/admin/cache/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_cached_entries"] >= 1
    assert stats["total_cache_hits"] >= 1
    assert stats["total_cost_saved_usd"] > 0.0


@pytest.mark.asyncio
async def test_create_and_use_virtual_key(client):
    """Verify admin key creation and using the new key for proxy requests."""
    admin_headers = {"X-Admin-Key": settings.ADMIN_SECRET_KEY}
    create_resp = await client.post(
        "/v1/admin/keys",
        headers=admin_headers,
        json={"name": "New Team Key", "max_budget": 0.50},
    )
    assert create_resp.status_code == 201
    new_key_data = create_resp.json()
    new_key = new_key_data["key_value"]
    assert new_key.startswith("gw-live-")
    assert new_key_data["max_budget"] == 0.50

    # Call proxy with the newly created key
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": "Testing new key"}],
    }
    proxy_resp = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {new_key}"},
        json=payload,
    )
    assert proxy_resp.status_code == 200


@pytest.mark.asyncio
async def test_dynamic_budget_exhaustion_after_first_call(client):
    """
    EDGE CASE:
    Create a key with a tiny budget ($0.0000001).
    Request #1 must succeed (200 OK) and push current_spend >= max_budget.
    Request #2 with the same key must immediately be blocked with HTTP 429,
    even if the prompt is in the exact-match cache.
    """
    admin_headers = {"X-Admin-Key": settings.ADMIN_SECRET_KEY}
    create_resp = await client.post(
        "/v1/admin/keys",
        headers=admin_headers,
        json={"name": "Micro Budget Key", "max_budget": 0.0000001},
    )
    assert create_resp.status_code == 201
    micro_key = create_resp.json()["key_value"]

    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": "Unique micro budget prompt test"}],
    }

    # 1st call: under budget prior to call -> 200 OK
    resp1 = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {micro_key}"},
        json=payload,
    )
    assert resp1.status_code == 200

    # 2nd call: spend now exceeds $0.0000001 -> must reject with 429 even though prompt is cached
    resp2 = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {micro_key}"},
        json=payload,
    )
    assert resp2.status_code == 429
    assert resp2.json()["detail"]["error"]["type"] == "budget_exceeded"


@pytest.mark.asyncio
async def test_openrouter_free_fallback_routing(client):
    """Verify that explicitly requesting openrouter/free routes cleanly and records usage."""
    payload = {
        "model": "openrouter/free",
        "messages": [{"role": "user", "content": "Test OpenRouter fallback model routing"}],
    }
    resp = await client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer gw-live-test"},
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["usage"]["total_tokens"] > 0


