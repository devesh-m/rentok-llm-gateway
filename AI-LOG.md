# AI-LOG.md

## 1. Which AI Tools & Models I Used, and for What
- **Tool:** Google Antigravity IDE (coding agent).
- **What I used it for:**
  - Scaffolding the FastAPI route structure (`chat.py`, `keys.py`, `usage.py`, `health.py`), SQLAlchemy async models, and Pydantic request/response schemas.
  - Writing the SHA-256 prompt normalization and cache lookup service (`cache_service.py`).
  - Building a single-page HTML/JS testing console at `GET /` so I could test requests, cache hits, and `429` budget blocks without clicking through Swagger UI bloat.
  - Writing the `pytest` suite (`tests/test_gateway.py`).

---

## 2. Where the AI Was Wrong or Misleading, and How I Caught It

### 1. Outdated Groq Model Names (`404 Model Not Found`)
The AI initially hardcoded `llama-3.3-70b-versatile` as the default primary model for Groq based on older training data. When I tested the live endpoint on FastAPI Cloud, requests were silently falling back to the mock responder because Groq had retired `llama-3.3-70b-versatile` and returned HTTP `404`. I checked the current Groq model documentation, switched the primary model to `openai/gpt-oss-20b` (and `meta-llama/llama-4-scout-17b-16e-instruct`), and added automatic model remapping in `llm_client.py` so callers passing legacy model strings don't fail.

### 2. Python 3.14 + `aiosqlite` Hanging on FastAPI Cloud
When deploying to FastAPI Cloud, the build defaulted to Python `3.14.3` because `requires-python = ">=3.11"` had no upper bound, and SQLite writes went to `./gateway.db` inside the container directory. The health check hung until FastAPI Cloud marked the deployment `verifying_failed`. I caught this by inspecting the container build logs, pinned `.python-version` to `3.12`, switched SQLite on Linux containers to `/tmp/gateway.db` with `NullPool`, and verified every fix locally with `pytest` before committing.

---

## 3. Where I Overrode the AI's Suggestion, and Why

1. **Replaced `gemini-1.5-flash` Fallback with OpenRouter (`openrouter/free`):**
   The AI originally wired Google Gemini (`gemini-1.5-flash`) as the secondary fallback provider. I overrode this and pointed the fallback to OpenRouter's free auto-router (`openrouter/free` on `https://openrouter.ai/api/v1/chat/completions`), which automatically routes each fallback request to an active `$0` model (such as `nvidia/nemotron-3-super-120b-a12b:free`) using the exact same OpenAI wire format.
2. **Used `httpx.AsyncClient` Instead of Provider-Specific SDKs:**
   Instead of installing separate `groq` and `openai` SDK packages, I kept all provider calls on raw `httpx.AsyncClient` requests against `/chat/completions`. That kept the dependency tree small and let both Groq and OpenRouter share identical timeout and error-handling logic.

---

## 4. How I Stayed in Control of Code I Didn't Type by Hand
- **Secrets & Environment Variables:** Verified that `GROQ_API_KEY`, `OPENROUTER_API_KEY`, and `ADMIN_SECRET_KEY` are only loaded through `pydantic-settings` from environment variables (`fastapi cloud env set`) and that `.env` and `*.db` are excluded in `.gitignore`.
- **Budget & Spend Math:** Checked `usage_service.py` and `pricing.py` line by line to verify that:
  1. `validate_virtual_key_and_budget()` runs *before* any upstream HTTP call is made and raises `HTTPException(429)` when `current_spend >= max_budget`.
  2. Spend updates execute an atomic SQL increment (`current_spend = current_spend + :cost`) using the exact `prompt_tokens` and `completion_tokens` returned by the provider.
  3. Cache hits (`X-Cache: HIT`) record `$0.00` spend against the key's budget while logging `cost_saved` separately.

---

## 5. Something I Learned from Scratch This Weekend
- **FastAPI Cloud Deployment & Container Lifecycle:** Learned how `fastapi deploy` builds containers with `uv`, how its post-deploy readiness probe verifies the container before switching traffic, and why SQLite on Linux containers needs `/tmp` + `NullPool` to avoid file-lock deadlocks across async workers.
- **OpenRouter Free Auto-Router (`openrouter/free`):** Learned how OpenRouter's `openrouter/free` meta-model dynamically selects the healthiest free upstream model per request and returns the resolved model ID (`nvidia/nemotron-3-super-120b-a12b:free`) in the response body.
