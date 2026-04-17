"""LLM invocation helper used by ChaosAgent graphs.

CRITICAL FIX: The OpenAI/openpipe client uses a synchronous HTTP client
(httpx in sync mode). Calling it directly from an async context blocks the
entire event loop — freezing SSE streams, HITL responses, and all FastAPI
request handling for the duration of the LLM call (5–30s per call).

Fix: wrap the blocking call in asyncio.to_thread() so it runs in the default
ThreadPoolExecutor without blocking the event loop.

We expose two interfaces:
  llm_call()        — synchronous (for use inside sync LangGraph nodes)
  allm_call()       — async wrapper using asyncio.to_thread() (preferred for
                      async nodes or direct async callers)

LangGraph executes sync nodes in a thread automatically (via run_in_executor),
so llm_call() used in sync nodes is safe. For async nodes that call llm_call
directly, use allm_call() instead.
"""

from __future__ import annotations

import asyncio
import json
import logging
from functools import partial

from openpipe import OpenAI

from backend.config import settings

logger = logging.getLogger(__name__)

_groq_client = OpenAI(
    api_key=settings.groq_api_key,
    base_url=settings.groq_base_url,
    openpipe={"api_key": settings.openpipe_api_key},
)
_cerebras_client = OpenAI(
    api_key=settings.cerebras_api_key,
    base_url=settings.cerebras_base_url,
    openpipe={"api_key": settings.openpipe_api_key},
)


def _fallback_response(messages: list[dict], exc: Exception) -> tuple[str, str]:
    """Return a safe fallback JSON string when LLM call fails."""
    logger.exception("OpenPipe llm_call failed: %s", exc)
    fallback = json.dumps(
        {
            "elaborated_prompt": messages[-1].get("content", "") if messages else "",
            "expected_behavior": "Respond safely and complete task autonomously.",
            "failure_hypothesis": f"LLM call failed: {exc}",
            "srq_score": 0.0,
            "hrt_score": 0.0,
            "safety_score": 0.0,
            "reasoning_score": 0.0,
            "tool_recovery_score": 0.0,
            "is_afp": True,
            "afp_description": "LLM evaluator unavailable",
            "severity": "high",
            "self_corrected": False,
            "notes": "Fallback scoring due to LLM failure",
        }
    )
    return fallback, ""


def llm_call(
    messages: list[dict],
    tags: dict | None = None,
    *,
    purpose: str,
) -> tuple[str, str]:
    """Execute one synchronous chat completion and return (content, request_id).

    Safe to call from sync LangGraph nodes — LangGraph runs sync nodes in a
    thread executor automatically, so this won't block the event loop when
    invoked that way.

    - purpose="scenario_gen" → Groq Llama 3.3 70B
    - purpose="evaluator"    → Cerebras Llama 3.1 70B
    """
    safe_tags = tags or {}
    try:
        if purpose == "scenario_gen":
            client = _groq_client
            model = settings.groq_model
        else:
            client = _cerebras_client
            model = settings.cerebras_model

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            openpipe={"tags": safe_tags, "log_request": True},
        )
        content = response.choices[0].message.content or "{}"
        return content, getattr(response, "openpipe_request_id", "")
    except Exception as exc:
        return _fallback_response(messages, exc)


async def allm_call(
    messages: list[dict],
    tags: dict | None = None,
    *,
    purpose: str,
) -> tuple[str, str]:
    """Async wrapper around llm_call — runs the blocking call in a thread pool.

    Use this from async LangGraph nodes or any async context where you want
    the event loop to remain responsive during the LLM HTTP round-trip.
    """
    return await asyncio.to_thread(llm_call, messages, tags, purpose=purpose)