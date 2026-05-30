"""
ChaosAgent LLM client — pure Groq + Cerebras, OpenPipe removed.

Two clients:
  - Groq (llama-3.3-70b-versatile)  → scenario generation, planning
  - Cerebras (llama3.1-70b)          → evaluation (fast inference)

Both use the OpenAI-compatible API via httpx under the hood.
Async wrapper uses asyncio.to_thread() to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from openai import OpenAI

from backend.config import settings

logger = logging.getLogger(__name__)

# ── Clients ───────────────────────────────────────────────────────────────────

_groq_client = OpenAI(
    api_key=settings.groq_api_key,
    base_url=settings.groq_base_url,
)

_cerebras_client = OpenAI(
    api_key=settings.cerebras_api_key,
    base_url=settings.cerebras_base_url,
)


# ── Fallback response ─────────────────────────────────────────────────────────

def _fallback_response(messages: list[dict], exc: Exception) -> tuple[str, str]:
    logger.exception("LLM call failed: %s", exc)
    fallback = json.dumps({
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
    })
    return fallback, ""


# ── Sync call ─────────────────────────────────────────────────────────────────

def llm_call(
    messages: list[dict],
    tags: dict | None = None,   # kept for API compatibility, no longer sent to OpenPipe
    *,
    purpose: str,
) -> tuple[str, str]:
    """
    Execute one synchronous chat completion.
    Returns (content, request_id).

    purpose="scenario_gen" → Groq  (fast generation)
    purpose="evaluator"    → Cerebras (fast eval)
    purpose="planner"      → Groq  (planning)
    """
    try:
        if purpose in ("scenario_gen", "scenario_gen_refine", "planner"):
            client = _groq_client
            model = settings.groq_model
        else:
            client = _cerebras_client
            model = settings.cerebras_model

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=600,
        )
        content = response.choices[0].message.content or "{}"
        return content, getattr(response, "id", "")
    except Exception as exc:
        return _fallback_response(messages, exc)


# ── Async wrapper ─────────────────────────────────────────────────────────────

async def allm_call(
    messages: list[dict],
    tags: dict | None = None,
    *,
    purpose: str,
) -> tuple[str, str]:
    """Async wrapper — runs blocking llm_call in thread pool."""
    return await asyncio.to_thread(llm_call, messages, tags, purpose=purpose)