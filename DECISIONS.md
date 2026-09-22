# DECISIONS.md (Work In Progress)

## 1. What We Are Building
A minimal, production-oriented LLM Gateway built with FastAPI that sits between client callers and upstream LLM providers (Groq and Google Gemini). It provides virtual API keys, per-key budget limits, usage tracking, and provider fallback resilience.

---

## 2. Initial Architectural Decisions

### Framework: FastAPI (Python 3.12)
- **Why:** High-performance async I/O suitable for proxying network requests, built-in Pydantic validation, and OpenAPI documentation.

### Datastore: SQLite (WAL Mode) with PostgreSQL Extensibility
- **Why:** Zero-configuration local development with sub-millisecond key lookups. Standard SQLAlchemy abstraction enables pointing to hosted PostgreSQL (e.g., Neon) for cloud deployments.

### Provider Strategy
- **Primary:** Groq (Llama 3.3 70B / 3.1 8B) for fast response times.
- **Fallback:** Google Gemini (Gemini 1.5 Flash) on rate limits, errors, or timeouts.

---
*Note: Detailed lifecycle traces, concurrency handling, and tradeoff analysis will be added as implementation progresses.*
