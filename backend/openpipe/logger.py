"""LLM invocation helper used by ChaosAgent graphs.

Fine-tuning/OpenPipe is intentionally deferred. This module provides a stable
call surface for graph nodes while routing requests to two OpenAI-compatible
providers:
- Groq (Scenario Generator)
- Cerebras (Evaluator)
"""

from __future__ import annotations

import json
import logging

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


def llm_call(messages: list[dict], tags: dict | None = None, *, purpose: str) -> tuple[str, str]:
    """Execute one chat completion call and return (content, request_id).

    - purpose="scenario_gen" routes to Groq Llama 3.3 70B
    - purpose="evaluator" routes to Cerebras Llama 3.1 70B
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

