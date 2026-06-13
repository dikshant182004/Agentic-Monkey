"""FastAPI application bootstrap for ChaosAgent backend services.

Fixes applied
─────────────
BUG C  LangSmith 401 spam: main.py lifespan unconditionally set
       LANGCHAIN_TRACING_V2=true even when LANGCHAIN_API_KEY is empty.
       Every LangGraph node invocation then fired a multipart ingest
       request to api.smith.langchain.com which returned 401, flooding
       the logs with WARNING lines and adding latency to every node.

       Fix: only enable tracing when langchain_api_key is non-empty.
       When the key is absent, LANGCHAIN_TRACING_V2 is forced to "false"
       so the LangSmith SDK skips all network calls entirely.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.api import agents, hitl, runs, steady_state
from backend.config import settings
from backend.db.session import AsyncSessionFactory
from backend.memory.redis_checkpointer import get_redis_checkpointer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configure tracing and verify infrastructure at startup."""
    if settings.langchain_api_key:
        # Only enable tracing when a real key is configured.
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        logger.info("LangSmith tracing enabled for project '%s'", settings.langchain_project)
    else:
        # Force tracing off — prevents 401 spam from the LangSmith SDK.
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        logger.info(
            "LangSmith tracing disabled (LANGCHAIN_API_KEY not set). "
            "Set it in .env to enable tracing."
        )

    if not settings.use_memory_saver:
        await get_redis_checkpointer()

    yield


app = FastAPI(title="ChaosAgent Backend", version=settings.app_version, lifespan=lifespan)

origins = [settings.streamlit_url] + [
    item.strip() for item in settings.extra_cors_origins.split(",") if item.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(steady_state.router)
app.include_router(runs.router)
app.include_router(hitl.router)

@app.get("/health")
async def health() -> tuple[dict, int] | dict:
    """Check PostgreSQL and Redis health including latency and error details."""
    top_status = "ok"
    postgres = {"status": "ok", "latency_ms": 0.0}
    redis_status = {"status": "ok", "latency_ms": 0.0}

    postgres_ok = False
    redis_ok = False

    pg_start = time.perf_counter()
    try:
        async with AsyncSessionFactory() as session:
            await session.execute(text("SELECT 1"))
        postgres["latency_ms"] = round((time.perf_counter() - pg_start) * 1000, 3)
        postgres_ok = True
    except Exception as exc:
        postgres = {"status": "error", "error": str(exc)}

    rd_start = time.perf_counter()
    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        await client.close()
        redis_status["latency_ms"] = round((time.perf_counter() - rd_start) * 1000, 3)
        redis_ok = True
    except Exception as exc:
        redis_status = {"status": "error", "error": str(exc)}

    if not postgres_ok or not redis_ok:
        top_status = "degraded"
    payload = {
        "status": top_status,
        "postgres": postgres,
        "redis": redis_status,
        "version": settings.app_version,
    }
    if not postgres_ok and not redis_ok:
        return JSONResponse(status_code=503, content=payload)
    return payload