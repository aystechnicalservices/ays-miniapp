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

import json
import logging

import httpx

from . import config

log = logging.getLogger("ays.gemini")

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# Pinned rather than "gemini-flash-latest": that alias can route to a
# preview/experimental backend (Google's own docs: "can be a stable,
# preview or experimental release... hot-swapped with every new release"),
# which 503'd under normal load in testing while this pinned GA version
# didn't. Update when Google deprecates this one too (it'll 404 with a
# message naming the replacement, same as it did for 2.0/2.5).
_MODEL = "gemini-3.6-flash"
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
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    # Every caller here is a classification/extraction task
                    # (match-or-draft, report facts, etc.), not creative
                    # writing — low temperature makes the same kind of input
                    # give the same judgment call consistently, rather than
                    # varying between calls near a decision boundary.
                    "generationConfig": {"temperature": 0.1},
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        log.exception("Gemini call failed")
        return None


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        if text[:4].lower() == "json":
            text = text[4:]
    return text.strip()


def _build_match_prompt(text: str, library: list) -> str:
    items_json = json.dumps(
        [{"id": i["id"], "villa": i["villa"], "section": i["section"], "text": i["text"]} for i in library]
    )
    return (
        "You are matching a boss's freeform task description against an existing "
        "library of villa-maintenance checklist items, or drafting a new one if "
        "nothing fits.\n\n"
        f"Existing library items (JSON array of id/villa/section/text):\n{items_json}\n\n"
        f"Boss's text: {json.dumps(text)}\n\n"
        "Match an existing item if its meaning is the same as the boss's text, even "
        "if worded differently — reuse it, do not create a near-duplicate. Only "
        "create a new item if nothing in the library fits. New item text must be "
        "short and imperative, matching the terse style of the existing items "
        '(e.g. "Trim the bonsai garden.", "Check for water leaks."). Correct any '
        "obvious spelling/grammar mistakes in the new text while keeping its "
        "meaning and any names intact.\n\n"
        "Return ONLY JSON, no prose, no markdown fences, in exactly this shape:\n"
        '{"match_id": <existing item id, or null>, "new": '
        '{"villa": "...", "section": "...", "text": "..."} or null}\n'
        "Exactly one of match_id/new must be non-null."
    )


async def match_or_draft_item(text: str, library: list):
    """Asks Gemini to either match `text` to an existing library item or
    draft a new one in its style. Returns (match_id, new_item, ai_used) —
    new_item is (villa, section, text) or None; ai_used is False whenever
    the caller should fall back to its own non-AI default (no API key, a
    network/parse failure, or the model naming a library id that doesn't
    actually exist — never trust a hallucinated id)."""
    library_list = list(library)
    response = await ask_gemini(_build_match_prompt(text, library_list))
    if response is None:
        return None, None, False

    valid_ids = {item["id"] for item in library_list}
    try:
        data = json.loads(_strip_json_fences(response))
        match_id = data.get("match_id")
        new = data.get("new")
        if match_id is not None:
            match_id = int(match_id)
            if match_id not in valid_ids:
                log.warning("Gemini matched a nonexistent library id %s", match_id)
                return None, None, False
            return match_id, None, True
        if new is not None:
            villa = str(new["villa"]).strip()
            section = str(new["section"]).strip()
            item_text = str(new["text"]).strip()
            if villa and section and item_text:
                return None, (villa, section, item_text), True
        return None, None, False
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        log.exception("Could not parse Gemini match/draft response: %r", response)
        return None, None, False
