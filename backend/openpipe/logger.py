"""OpenPipe-backed LLM invocation helper for all model calls."""

from __future__ import annotations

import json
import logging

from openpipe import OpenAI

from backend.config import settings

logger = logging.getLogger(__name__)
openpipe_client = OpenAI(api_key=settings.openai_api_key, openpipe={"api_key": settings.openpipe_api_key})


def llm_call(messages: list[dict], tags: dict | None = None) -> tuple[str, str]:
    """Execute one chat completion call and return content with OpenPipe request id."""
    safe_tags = tags or {}
    try:
        response = openpipe_client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            openpipe={"tags": safe_tags, "log_request": True},
        )
        content = response.choices[0].message.content or "{}"
        return content, getattr(response, "openpipe_request_id", "")
    except Exception as exc:
        logger.exception("OpenPipe llm_call failed")
        fallback = json.dumps(
            {
                "elaborated_prompt": messages[-1].get("content", ""),
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

