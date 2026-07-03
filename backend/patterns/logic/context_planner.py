"""Turn a spoken/typed occasion note into temporary pattern adjustments.

Flow:  audio → (Groq Whisper) transcript → (Groq LLM) plan → validate → preview.

The LLM knows the Indian festival calendar and the home's learned patterns, and
proposes a small set of TEMPORARY, dated adjustments (add/shift/suppress/adjust)
that overlay the routines for the occasion. Every shift/suppress/adjust must
reference a REAL learned pattern (resolve-or-drop) so nothing is hallucinated.
The base patterns are never modified; the user confirms before anything applies.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timedelta, timezone

import httpx

from patterns.app.config import get_settings
from patterns.logic import pattern_service
from patterns.logic.narrator import _call_groq, _verify_ctx

logger = logging.getLogger(__name__)

GROQ_WHISPER_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

_VALID_TYPES = {"add", "shift", "suppress", "adjust"}

SYSTEM_PROMPT = """You adapt a home's LEARNED daily routines to a one-off occasion the user mentions
— guests visiting, a festival, a party, travel, or someone unwell. You know the
Indian festival calendar (Diwali, Navratri, Holi, Raksha Bandhan, Pongal, Eid,
Christmas, etc.) and typical Indian-household customs.

You are given: the user's note, TODAY's date, the home's learned patterns (JSON,
each with a pattern_id, device, action and usual time), and the known devices.

Produce a SMALL set (3–6) of TEMPORARY adjustments for the relevant day — never
permanent changes. Adjustment types:
  - "add"      : a new temporary action (device + action + new_time).
  - "shift"    : move an existing pattern's time (target_pattern_id + new_time).
  - "suppress" : skip an existing pattern that day (target_pattern_id).
  - "adjust"   : a qualitative tweak to an existing pattern (target_pattern_id +
                 description), e.g. play festival bhajans instead of the usual.

Rules:
- shift / suppress / adjust MUST reference a real pattern_id from the list.
- Prefer the home's actual devices; you may "add" a sensible new device
  (e.g. decoration_lights) when the occasion clearly calls for it.
- Be concrete and culturally appropriate (festival → more diyas/lights, earlier &
  longer pooja, festival bhajans; guests → cool the room earlier, decoration
  lights on, upbeat music, maybe skip noisy chores).
- Resolve the occasion's DATE from the note relative to today (ISO YYYY-MM-DD).

Return STRICT JSON:
{"occasion":"<short>","occasion_date":"YYYY-MM-DD","summary":"<one line>",
"adjustments":[{"type":"add|shift|suppress|adjust","target_pattern_id":"<id|null>",
"device":"<id|null>","action":"ON|OFF|null","new_time":"HH:MM|null",
"description":"<what changes>","reason":"<why, tied to the occasion>"}]}"""


async def transcribe(audio_base64: str, fmt: str = "webm") -> str:
    """Groq Whisper STT. Accepts webm/wav/mp3 directly. Returns '' on failure."""
    s = get_settings()
    if not s.groq_api_key:
        return ""
    try:
        audio = base64.b64decode(audio_base64)
        async with httpx.AsyncClient(timeout=30.0, verify=_verify_ctx()) as client:
            resp = await client.post(
                GROQ_WHISPER_URL,
                headers={"Authorization": f"Bearer {s.groq_api_key}"},
                files={"file": (f"note.{fmt}", audio, f"audio/{fmt}")},
                data={"model": "whisper-large-v3-turbo", "response_format": "json"},
            )
        if resp.status_code != 200:
            logger.error("Whisper error %s: %s", resp.status_code, resp.text[:200])
            return ""
        return resp.json().get("text", "").strip()
    except Exception as e:  # pragma: no cover - network
        logger.error("Whisper call failed: %s: %s", type(e).__name__, e)
        return ""


def _pattern_brief(patterns) -> tuple[list[dict], set[str], set[str]]:
    """Compact patterns for the LLM + the sets of valid ids/devices."""
    brief, ids, devices = [], set(), set()
    for p in patterns:
        t = getattr(p, "usual_time", None) or getattr(p, "usual_start_time", None)
        dev = getattr(p, "device", None)
        row = {
            "pattern_id": p.pattern_id,
            "device": dev,
            "action": getattr(p, "action", None),
            "time": t,
            "type": p.pattern_type.value,
        }
        if isinstance(getattr(p, "description", None), str):
            row["description"] = p.description
        brief.append(row)
        ids.add(p.pattern_id)
        if dev:
            devices.add(dev)
    return brief, ids, devices


def _validate(adjustments: list, valid_ids: set[str]) -> list[dict]:
    """Keep only well-formed adjustments; drop hallucinated pattern references."""
    out = []
    for a in adjustments or []:
        if not isinstance(a, dict):
            continue
        atype = (a.get("type") or "").lower()
        if atype not in _VALID_TYPES:
            continue
        if atype in {"shift", "suppress", "adjust"}:
            if a.get("target_pattern_id") not in valid_ids:
                continue  # resolve-or-drop — no hallucinated targets
        if atype == "add" and not a.get("device"):
            continue
        if not a.get("description"):
            continue
        out.append({
            "type": atype,
            "target_pattern_id": a.get("target_pattern_id"),
            "device": a.get("device"),
            "action": a.get("action"),
            "new_time": a.get("new_time"),
            "description": a.get("description"),
            "reason": a.get("reason", ""),
        })
    return out


async def plan(household_id: str, text: str, *, now: datetime | None = None) -> dict:
    """Produce a previewable ContextPlan dict from the user's note."""
    now = now or datetime.now(timezone.utc)
    patterns = pattern_service.get_patterns(household_id)
    brief, valid_ids, devices = _pattern_brief(patterns)

    settings = get_settings()
    user_payload = {
        "note": text,
        "today": now.date().isoformat(),
        "tomorrow": (now + timedelta(days=1)).date().isoformat(),
        "known_devices": sorted(devices),
        "learned_patterns": brief,
    }
    llm = await _call_groq(SYSTEM_PROMPT, json.dumps(user_payload), settings)

    if not isinstance(llm, dict):
        return {
            "household_id": household_id, "transcript": text, "occasion": "",
            "occasion_date": (now + timedelta(days=1)).date().isoformat(),
            "summary": "Couldn't reach the planner — please try again.",
            "adjustments": [], "llm_powered": False,
        }

    adjustments = _validate(llm.get("adjustments"), valid_ids)
    return {
        "household_id": household_id,
        "transcript": text,
        "occasion": llm.get("occasion", ""),
        "occasion_date": llm.get("occasion_date")
        or (now + timedelta(days=1)).date().isoformat(),
        "summary": llm.get("summary", ""),
        "adjustments": adjustments,
        "llm_powered": True,
    }
