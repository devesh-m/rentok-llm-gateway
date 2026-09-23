# DECISIONS.md

## 1. What I Built
I built a lightweight HTTP LLM gateway in Python (FastAPI) that proxies OpenAI-compatible chat completion requests (`/v1/chat/completions`) to Groq as the primary provider and OpenRouter (`openrouter/free`) as the fallback. Callers authenticate using gateway-issued virtual keys (`gw-live-...`) so real upstream API keys never leave the server. Every request checks the key's remaining USD budget before forwarding, logs prompt/completion tokens and cost in SQLite, and caches exact-match responses (`X-Cache: HIT/MISS`) to avoid paying twice for identical prompts.

---

## 2. Moving Parts & Request Lifecycle

```text
Client (POST /v1/chat/completions + Authorization: Bearer gw-live-test)
  │
  ├─► 1. Auth & Budget Check (usage_service.py)
  │      Look up virtual key in SQLite `virtual_keys`.
  │      If key is missing/inactive -> HTTP 401.
  │      If current_spend >= max_budget -> HTTP 429 Too Many Requests.
  │
  ├─► 2. Exact-Match Cache Lookup (cache_service.py)
  │      Hash normalized (model, messages, temperature, max_tokens) with SHA-256.
  │      If found in `response_cache` -> log $0.00 request, set `X-Cache: HIT`, return immediately.
  │
  ├─► 3. Upstream Provider Dispatch (llm_client.py)
  │      Try Primary: Groq (`openai/gpt-oss-20b`).
  │      If Groq times out (15s), rate-limits (429), or 5xx errors ->
  │      Fall back to Secondary: OpenRouter (`openrouter/free`).
  │
  ├─► 4. Usage & Spend Logging (usage_service.py + pricing.py)
  │      Read `prompt_tokens` and `completion_tokens` from provider response.
  │      Compute USD cost from per-1M-token rate table.
  │      Insert row into `usage_logs` and atomically increment `virtual_keys.current_spend`.
  │      Save response payload into `response_cache`.
  │
  └─► 5. Response Returned to Caller
         Standard OpenAI JSON schema + `gateway_metadata` (provider, latency_ms, cost_usd).
```

---

## 3. Most Important Decisions

### 1. Non-Streaming JSON vs. SSE Streaming
- **Options considered:** Server-Sent Events (`stream: true`) vs. synchronous JSON (`stream: false`).
- **Picked:** Non-streaming JSON.
- **Tradeoff accepted:** Higher time-to-first-token for interactive chat UIs, in exchange for exact token accounting. In non-streaming mode, upstream providers return authoritative `prompt_tokens` and `completion_tokens` in the response body before we commit spend to the database. With streaming, a client disconnect mid-stream forces you to estimate tokens via a local tokenizer (`tiktoken`) and complicates post-request budget updates.

### 2. Budgeting in USD ($) vs. Request or Token Counts
- **Options considered:** Capping by request count, raw token count, or estimated USD cost.
- **Picked:** USD cost calculated from a per-model pricing table (`app/services/pricing.py`).
- **Tradeoff accepted:** We have to maintain a pricing dictionary in code when models change. However, request caps ignore prompt length (a 50-token prompt and an 8,000-token prompt count the same), and token caps break when routing across different models with different costs. Even on free-tier providers (`openrouter/free`), tracking shadow USD cost lets us test realistic budget enforcement (`$1.00` cap on `gw-live-test`, `$0.00` on `gw-live-exhausted`).

### 3. SQLite (WAL Mode) vs. Hosted Postgres / Redis
- **Options considered:** Redis, hosted Postgres (Neon/Supabase), or embedded SQLite with Write-Ahead Logging (`aiosqlite`).
- **Picked:** SQLite in WAL mode (`/tmp/gateway.db` on FastAPI Cloud, `./gateway.db` locally) via async SQLAlchemy.
- **Tradeoff accepted:** Container restarts on a single-node PaaS wipe `/tmp/gateway.db` (which is why `init_db()` re-seeds the test keys on startup), and SQLite only scales to a single container instance. The benefit is zero network round-trip latency (<0.5ms for key lookups vs. 20–50ms to a remote cloud DB) and zero external database credentials needed to run or review the project.

### 4. Synchronous Pre/Post Logging vs. Background Queue
- **Options considered:** `FastAPI.BackgroundTasks` / Redis queue vs. awaiting the DB write inside the request lifecycle.
- **Picked:** Synchronous `await` before returning the response.
- **Tradeoff accepted:** Adds ~1–2ms of SQLite write latency to the HTTP response, but guarantees that `current_spend` is updated immediately so the very next sequential request sees the new balance.

---

## 4. First-Principles: Why Enforce Budgets at the Gateway Instead of Trusting Callers?
Callers cannot be trusted to enforce their own budgets for two reasons:
1. **Buggy client code is the #1 cause of runaway LLM bills.** An accidental `while True` retry loop or an unguarded frontend endpoint will happily ignore client-side limits and burn through upstream provider credits in minutes.
2. **Shared state across multiple callers.** Even well-behaved services don't know what other workers or scripts sharing the same virtual key have spent in the last second. Only the gateway sits in the critical path of every request and holds a single source of truth for cumulative spend.

---

## 5. Concurrency: Two Requests on a Near-Exhausted Key Hitting at Once
- **What happens:** Suppose `gw-live-test` has `$0.0001` remaining and two concurrent requests (`R1` and `R2`) arrive at the exact same millisecond. Both read `current_spend < max_budget` during the pre-check (`validate_virtual_key_and_budget`), so **both are allowed upstream**. When they return (~600ms later), both execute an atomic SQL increment (`UPDATE virtual_keys SET current_spend = current_spend + :cost`). No spend data is lost, but the key's final `current_spend` can slightly overshoot `max_budget` by the cost of one in-flight request before subsequent requests get blocked with `429`.
- **Did I handle it or knowingly not?** I handled the **write race** (using an atomic SQL `current_spend + :cost` update instead of read-modify-write in Python), and **knowingly accepted the pre-check race**. Fixing the pre-check race requires either serializing all LLM requests per key with a pessimistic lock (which kills concurrency for 1+ second per call) or reserving an estimated `max_tokens * rate_out` hold before calling the provider and refunding the difference afterward. For a minimal gateway, a 1-request soft overshoot is a standard and pragmatic trade-off.

---

## 6. Fallback Policy
1. **Primary (`groq`):** Send to Groq (`openai/gpt-oss-20b`) with a 15-second timeout. If the caller passes a deprecated or unknown model name (like `gpt-4o` or `llama-3.3-70b-versatile`), the gateway remaps it to `openai/gpt-oss-20b` so requests don't 404.
2. **Secondary (`openrouter`):** If Groq returns HTTP `429`, `5xx`, or times out, the gateway catches the error and routes the prompt to OpenRouter's free auto-router (`openrouter/free`), which picks the healthiest available free model (e.g. `nvidia/nemotron-3-super-120b-a12b:free`).
3. **Final fail-safe (`mock`):** If both providers are down or credentials aren't set in local testing, a deterministic mock responder returns a structured response so the budget and logging pipeline can still be tested offline.

---

## 7. What I Deliberately Did NOT Build (and Why)
- **SSE Streaming (`stream: true`):** Cut to keep token counting and cost deduction deterministic from the provider's `usage` block.
- **Semantic Vector Caching (Embeddings / FAISS):** I built SHA-256 exact-match caching instead. Running an embedding model on every incoming prompt adds 50–150ms of latency and risks serving false-positive cached answers when two prompts differ by a single negation word ("is" vs "is not").
- **Multi-tenant user login / RBAC:** Cut per the spec; static admin secret (`X-Admin-Secret`) + virtual keys (`gw-live-...`) cover the core requirement.

---

## 8. The One Decision I'm Least Confident About
**Using local SQLite (`/tmp/gateway.db`) in production instead of an external Postgres database.**
- **Case for SQLite:** It keeps the codebase self-contained, requires zero external cloud DB provisioning, and gives sub-millisecond reads/writes since the DB lives in the same container memory/disk space as FastAPI.
- **Case against SQLite:** On FastAPI Cloud, `/tmp/gateway.db` is ephemeral across deployments or container restarts, and if the service scales to 2+ replicas behind a load balancer, each replica would have its own separate SQLite file—meaning a key could spend its `$1.00` budget once per replica.

---

## 9. Where It Breaks & What I'd Do With One More Week
1. **Multi-replica state split & ephemeral storage:** Move `DATABASE_URL` from SQLite to managed Postgres (Neon) + Redis for distributed atomic budget counters (`INCRBYFLOAT`).
2. **Pre-flight budget reservation:** Reserve `max_tokens * completion_rate` prior to calling the upstream LLM and reconcile the unused amount once the actual `completion_tokens` return, closing the concurrent overshoot window.
3. **Per-key rate limiting (RPM/TPM):** Add a sliding-window rate limiter alongside the total USD cap so a single burst can't exhaust upstream provider rate limits for other keys.
