from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import init_db
from app.routes import chat, keys, usage, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB tables and seed test virtual keys
    await init_db()
    yield
    # Shutdown logic (if any)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description=(
        "Production-grade Minimal LLM Gateway providing virtual API keys, "
        "hard budget enforcement, usage & spend logging, and multi-provider fallback resilience."
    ),
    lifespan=lifespan,
)

# Enable CORS for cross-origin client apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
app.include_router(chat.router)
app.include_router(keys.router)
app.include_router(usage.router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)

