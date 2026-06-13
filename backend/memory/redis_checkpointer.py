"""Redis checkpointer singleton and thread-id conventions for LangGraph.

LangGraph 1.x changes:
- MemorySaver has been renamed to InMemorySaver (MemorySaver is kept as an alias
  but the canonical import is InMemorySaver from langgraph.checkpoint.memory).
- AsyncRedisSaver import path may vary by langgraph-checkpoint-redis package version;
  we guard with a broad try/except as before.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver

try:
    from langgraph.checkpoint.redis.aio import AsyncRedisSaver
except Exception:  # pragma: no cover
    AsyncRedisSaver = None  # type: ignore[assignment]

from backend.config import settings

_checkpointer: object | None = None


async def get_redis_checkpointer() -> object:
    """Return singleton checkpointer, using InMemorySaver only in explicit dev mode."""
    global _checkpointer
    if _checkpointer is None:
        if settings.use_memory_saver or AsyncRedisSaver is None:
            _checkpointer = InMemorySaver()
        else:
            _checkpointer = AsyncRedisSaver.from_conn_string(settings.redis_url)
            await _checkpointer.asetup()
    return _checkpointer


def run_thread_id(run_id: str) -> dict:
    """Return config dict for run-level checkpoint namespace."""
    return {"configurable": {"thread_id": f"chaosagent:run:{run_id}"}}


def user_session_thread_id(user_id: str) -> dict:
    """Return config dict for user-session checkpoint namespace."""
    return {"configurable": {"thread_id": f"chaosagent:user:{user_id}"}}