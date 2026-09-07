"""Gemini API plumbing — one function, no framework, no agent.

ask_gemini() is a single stateless call: send a prompt string, get a
response string back (or None on any failure whatsoever). Every caller owns
everything else — parsing the JSON it asked for, deciding what to do with
it, falling back to plain non-AI behavior when this returns None. The model
never marks a task done and never sends a plan; it only ever proposes
text/ids that existing, deterministic code goes on to act on.

Talks to the REST API directly over httpx (already a dependency via
python-telegram-bot) rather than the official google-genai SDK, which
requires pydantic>=2 — a hard conflict with this app's pydantic v1 pin,
itself required to avoid a pydantic-core Rust build that doesn't compile
under Termux. One HTTP POST is all this needs anyway.
"""

import logging

import httpx

from . import config

log = logging.getLogger("ays.gemini")

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_MODEL = "gemini-flash-latest"
_TIMEOUT = 30.0


async def ask_gemini(prompt: str):
    """Returns Gemini's text response to prompt, or None on any failure —
    missing API key, network error, bad response, unexpected shape. Callers
    must treat None as "fall back to non-AI behavior", never as an error to
    surface to the user."""
    if not config.GEMINI_API_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                _ENDPOINT.format(model=_MODEL),
                params={"key": config.GEMINI_API_KEY},
                json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]},
            )
            resp.raise_for_status()
            data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        log.exception("Gemini call failed")
        return None
