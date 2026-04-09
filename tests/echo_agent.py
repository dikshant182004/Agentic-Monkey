"""Local dummy Agent2Agent target agent for manual end-to-end testing.

This black-box service simply echoes the incoming prompt back as `response`.
It is used to verify ChaosAgent A2A + chaos orchestration wiring locally.
"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Echo Agent2Agent Demo")


@app.post("/chat")
async def chat(payload: dict) -> dict:
    """Accept arbitrary JSON and echo the `message` field as response."""
    message = payload.get("message", "")
    session_id = payload.get("session_id", "")
    return {"response": f"[ECHO session_id={session_id}] {message}"}

