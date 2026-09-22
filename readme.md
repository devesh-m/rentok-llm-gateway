# RentOk Minimal LLM Gateway

A high-performance, resilient, and production-grade LLM Gateway built with **FastAPI**. It acts as an intelligent intermediary between client applications and upstream LLM providers (Groq and Google Gemini), adding virtual API keys, per-key budget caps, token/cost spend logging, multi-provider fallback resilience, and response caching.

---

## Features
- **Virtual API Keys:** Client applications authenticate using gateway-issued keys (`gw-live-xxxx`). Upstream provider credentials remain strictly isolated server-side.
- **Hard Budget Enforcement:** Each virtual key has a configurable spending cap in USD ($). If exceeded, requests are cleanly blocked with HTTP `429 Too Many Requests`.
- **Granular Usage & Spend Logging:** Every proxied request records prompt/completion tokens, calculated costs, provider, and latency into an ACID-compliant datastore.
- **Multi-Provider Fallback Resilience:** Automatically falls back from Primary (Groq / Llama 3.3 70B) to Secondary (Google Gemini / Flash) on timeouts, rate limits (429), or server errors (5xx).
- **Smart Response Caching (Stretch Goal):** Bypasses upstream LLM inference for identical queries, returning responses in <5ms with `X-Cache: HIT` while measuring cumulative cost savings.

---

## Deliverables & Documentation
- [DECISIONS.md](DECISIONS.md): Architectural decisions, request lifecycle trace, first-principles reasoning, concurrency analysis, and failure mode trade-offs.
- [AI-LOG.md](AI-LOG.md): Comprehensive, honest log of AI usage, verification points, and overrides.

---

## Quick Start (Local Development)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment
Copy `.env.example` to `.env` and add your provider keys (optional for testing):
```bash
cp .env.example .env
```

### 3. Run Gateway
```bash
python -m fastapi dev app/main.py
```
Interactive API documentation will be available at [http://localhost:8000/docs](http://localhost:8000/docs).