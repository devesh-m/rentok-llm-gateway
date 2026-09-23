# RentOk Minimal LLM Gateway

A high-performance, resilient, and production-grade LLM Gateway built with **FastAPI**. It acts as an intelligent intermediary between client applications and upstream LLM providers (Groq and OpenRouter `openrouter/free`), adding virtual API keys, per-key budget caps, token/cost spend logging, multi-provider fallback resilience, and response caching.

---

## Live Production Deployment
- **Live Gateway Console & Spend Dashboard:** [https://rentok-llm-gateway.fastapicloud.dev](https://rentok-llm-gateway.fastapicloud.dev)
- **Interactive API Docs (Swagger UI):** [https://rentok-llm-gateway.fastapicloud.dev/docs](https://rentok-llm-gateway.fastapicloud.dev/docs)
- **Health Check:** [https://rentok-llm-gateway.fastapicloud.dev/health](https://rentok-llm-gateway.fastapicloud.dev/health)

### Working Example Request (`curl`)
```bash
curl -X POST https://rentok-llm-gateway.fastapicloud.dev/v1/chat/completions \
  -H "Authorization: Bearer gw-live-test" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-oss-20b",
    "messages": [
      {"role": "user", "content": "Hello! Explain what an LLM gateway does in one sentence."}
    ]
  }'
```

### Check Spend & Usage (`curl`)
```bash
curl "https://rentok-llm-gateway.fastapicloud.dev/v1/admin/usage?key=gw-live-test"
```

### Test Budget Enforcement (Returns HTTP 429)
```bash
curl -i -X POST https://rentok-llm-gateway.fastapicloud.dev/v1/chat/completions \
  -H "Authorization: Bearer gw-live-exhausted" \
  -H "Content-Type: application/json" \
  -d '{"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": "Hello"}]}'
```

---

## Features
- **Virtual API Keys:** Client applications authenticate using gateway-issued keys (`gw-live-xxxx`). Upstream provider credentials remain strictly isolated server-side.
- **Hard Budget Enforcement:** Each virtual key has a configurable spending cap in USD ($). If exceeded, requests are cleanly blocked with HTTP `429 Too Many Requests`.
- **Granular Usage & Spend Logging:** Every proxied request records prompt/completion tokens, calculated costs, provider, and latency into an ACID-compliant datastore.
- **Multi-Provider Fallback Resilience:** Automatically falls back from Primary (Groq / `openai/gpt-oss-20b`) to Secondary (OpenRouter Free Auto-Router / `openrouter/free`, e.g. `nvidia/nemotron-3-super-120b-a12b:free`) on timeouts, rate limits (429), or server errors (5xx).
- **Smart Response Caching (Stretch Goal):** Bypasses upstream LLM inference for identical queries, returning responses in <5ms with `X-Cache: HIT` while measuring cumulative cost savings (`GET /v1/admin/cache/stats`).

---

## Deliverables & Documentation
- [DECISIONS.md](DECISIONS.md): Architectural decisions, request lifecycle trace, first-principles reasoning, concurrency analysis, and failure mode trade-offs.
- [AI-LOG.md](AI-LOG.md): Comprehensive, honest log of AI usage, verification points, and overrides.