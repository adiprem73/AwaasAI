"""Gemini audio understanding — the household "ear" that actually hears.

A text LLM (Groq/Bedrock) cannot process sound. Google Gemini is *audio-native*:
given a short mic clip it identifies ANY household sound in open vocabulary — a
pressure-cooker whistle, a mixer-grinder, a temple bell, a baby crying — using
world knowledge, and reasons an appropriate action. This is the piece that lets
the listener detect sounds "on its own" instead of relying on a fixed class list.

Free Google AI Studio tier — set ``GEMINI_API_KEY`` in ``backend/.env``. The call
degrades gracefully: on any failure the caller falls back to the deterministic
taxonomy / simulate path, so the feature never hard-blocks.
"""
from __future__ import annotations

import json
import logging

import httpx

from patterns.app.config import get_settings
from patterns.logic.ambient_sounds import SOUNDS
from patterns.logic.narrator import _call_groq, _verify_ctx  # reuse proven helpers

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the "ear" of an Indian smart-home assistant. You LISTEN to a short audio
clip recorded in a home and identify the household sound(s) present, then reason
about what it means and what to do. You know Indian-household sounds well:
pressure-cooker whistle, mixer-grinder, kadai/tadka sizzle, temple bell & aarti,
pressure/steam, exhaust fan, doorbell, milkman/vendor calls, baby crying,
coughing, a fall, glass breaking, smoke/fire alarm, tap/RO water, etc.

Return ONLY strict JSON (no prose) with this shape:
{
  "primary_sound": "<short open-vocabulary name of the main sound>",
  "sound_key": "<the best-matching key from the provided list, or 'other'>",
  "description": "<one sentence: what is happening>",
  "likely_activity": "<one short phrase: the household activity implied>",
  "category": "cooking|safety|care|security|comfort|activity",
  "urgency": "info|suggest|warn|alert",
  "suggested_action": {"device": "<device id or ''>", "action": "ON|OFF|OPEN|CLOSE|''"} ,
  "prompt": "<one short, caring Alexa-style line to say to the user>"
}
Rules:
- If no clear/meaningful household sound is present, set sound_key to "other",
  urgency "info", suggested_action {"device":"","action":""}, and say so plainly.
- Only suggest an action when it clearly helps (e.g. gas OFF for a finished
  pressure cooker or a smoke alarm). Otherwise leave device/action empty.
- Keep prompt under 25 words, warm and specific to Indian home life."""


def _known_keys_block() -> str:
    lines = [f"- {s.key}: {s.label} ({s.category})" for s in SOUNDS]
    return "\n".join(lines)


async def listen(audio_base64: str, mime_type: str, context: dict) -> dict | None:
    """Send a clip to Gemini; return the parsed JSON interpretation, or None."""
    s = get_settings()
    if not s.gemini_api_key:
        logger.info("Ambient listen: GEMINI_API_KEY not set.")
        return None

    user_text = (
        "Known sound keys you may use for `sound_key` (else 'other'):\n"
        f"{_known_keys_block()}\n\n"
        "Live house context (use it to judge urgency/action):\n"
        f"- time: {context.get('current_time') or 'now'}\n"
        f"- people home: {', '.join(context.get('people_home') or []) or 'unknown'}\n"
        f"- devices currently ON: {', '.join(context.get('active_devices') or []) or 'none'}\n\n"
        "Listen to the attached audio and return the JSON."
    )

    url = f"{s.gemini_base_url}/models/{s.gemini_model}:generateContent?key={s.gemini_api_key}"
    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{
            "parts": [
                {"text": user_text},
                {"inline_data": {"mime_type": mime_type, "data": audio_base64}},
            ]
        }],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.2,
            "maxOutputTokens": 700,
        },
    }

    try:
        async with httpx.AsyncClient(
            timeout=s.gemini_timeout_seconds, verify=_verify_ctx()
        ) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            logger.error("Gemini audio error %s: %s", resp.status_code, resp.text[:300])
            return None
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return json.loads(text)
    except (KeyError, IndexError):
        logger.error("Gemini audio: unexpected response shape.")
        return None
    except json.JSONDecodeError:
        logger.warning("Gemini audio: non-JSON reply.")
        return None
    except Exception as e:  # pragma: no cover - network
        logger.error("Gemini audio call failed: %s: %s", type(e).__name__, e)
        return None


# ─── Narration of a FLAGGED sound (Groq text LLM) ────────────────────────────

_NARRATE_SYSTEM = """You are Alexa, the caring voice of an Indian smart home. A deterministic engine
has already decided a household SOUND is worth surfacing and WHY (it gives you the
sound, the reason it's notable, the supporting numbers, and the live context —
time, who's home, devices on). Your ONLY job is to phrase ONE short, warm, human
line to say aloud, plus a brief 'why'.

Rules:
- Trust the engine's decision and numbers — do NOT invent new facts or numbers.
- If a `reason` is given, your line MUST reflect that SPECIFIC insight (e.g. "the
  cooker has whistled more than usual", "coughing repeatedly") — not a generic
  remark. Weave in the concrete number from `evidence` when it's telling.
- Match urgency to severity: calm/gentle for info, concerned for warn, urgent and
  action-first for alert. Never alarm the family unnecessarily.
- Be specific to Indian home life, under 30 words for the line.
Return ONLY JSON: {"line": "<spoken line>", "explanation": "<one short why>"}"""


async def narrate(payload: dict) -> dict:
    """Phrase a flagged sound as a caring Alexa line. Falls back gracefully."""
    settings = get_settings()
    res = await _call_groq(_NARRATE_SYSTEM, json.dumps(payload), settings)
    if isinstance(res, dict) and res.get("line"):
        return {
            "narration": str(res["line"]).strip(),
            "explanation": str(res.get("explanation", "")).strip(),
            "narration_llm": True,
        }
    # Deterministic fallback line so the UI always speaks.
    reason = payload.get("reason") or ""
    base = payload.get("prompt") or payload.get("meaning") or "I noticed a household sound."
    line = f"{base} {reason}".strip() if reason else base
    return {"narration": line, "explanation": reason, "narration_llm": False}
