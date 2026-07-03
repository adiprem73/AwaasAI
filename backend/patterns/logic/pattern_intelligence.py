"""LLM contextual-pattern generator — the "smarter" half of the pattern engine.

Pipeline (see docs/HACKATHON_DEMOS_SPEC.md · Demo 1):

    deterministic base patterns  ─┐
    per-day context feature table ─┼─▶  LLM proposes conditional rules
                                   ┘         │
                                             ▼
                        deterministic verification (day_features)
                                             │  keep only rules the data backs
                                             ▼
                               verified ConditionalPattern[]  (+ "active now")

The LLM only *proposes* — every rule is re-measured against real history here, so
a hallucinated rule can never survive. If the LLM is unavailable, a deterministic
fallback brute-forces a small feature grid so the demo still produces results.
"""
from __future__ import annotations

import json
import logging

import httpx

from patterns.app.config import get_settings
from patterns.logic import day_features as df
from patterns.logic.narrator import _verify_ctx  # reuse the proven SSL context
from patterns.models.contextual import Condition, ConditionalPattern
from patterns.models.events import Event
from patterns.models.patterns import BasePattern

logger = logging.getLogger(__name__)

# Verified-rule quality gate (verification also enforces its own thresholds).
_MIN_CONFIDENCE = 0.45

SYSTEM_PROMPT = """You are a household-routine analyst. A deterministic engine has already mined
plain routines from 30 days of smart-home events. Your job is to find CONDITIONAL
routines it cannot express: behaviours that depend on an external condition.

You are given (1) the base routines, (2) a day-by-day table where each row has the
weekday, whether it is a weekend, that day's outdoor temperature, who arrived
home, and the first ON-time of each device that day (null = the device did not
turn on that day).

Find rules of the form: a device's (action) DEPENDS ON a condition. Two kinds:
  - "occurrence": the device only turns on when the condition holds
    (e.g. AC only on hot days).
  - "time_shift": the device turns on but at a DIFFERENT time when the condition
    holds (e.g. porch light ~1h later on weekends).

Rules:
- Only use these condition features: temperature_c (number, °C), is_weekend
  (true/false), dow ("Mon".."Sun"), season, and arrived:<person> / active:<person>
  (true/false) for people you see in the table.
- NEVER invent devices or people not present in the data.
- Propose only rules the table visibly supports. Prefer the feature that best
  explains the behaviour (e.g. arrived:mother over is_weekend if it fits better).
- Return STRICT JSON only:
{"patterns":[{"device":"<id>","action":"ON","kind":"occurrence|time_shift",
"condition":{"feature":"<feature>","op":">|<|>=|<=|==|!=","value":<number|bool|string>},
"human_label":"<short name>","claim":"<one sentence>"}]}
"""


def _base_summary(patterns: list[BasePattern]) -> list[str]:
    out = []
    for p in patterns:
        t = getattr(p, "usual_time", None) or getattr(p, "usual_start_time", None)
        dev = getattr(p, "device", None) or getattr(p, "description", p.pattern_type.value)
        act = getattr(p, "action", "")
        when = f" ~{t}" if t else ""
        out.append(f"{dev} {act}{when} (conf {p.confidence})")
    return out


async def _call_groq_json(system: str, user_msg: str, settings) -> dict | None:
    """Groq chat-completion in JSON mode — mirrors logic/narrator._call_groq."""
    if not settings.groq_api_key:
        logger.info("Contextual patterns: GROQ_API_KEY not set — using fallback.")
        return None
    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
    }
    try:
        async with httpx.AsyncClient(
            timeout=settings.narrator_timeout_seconds, verify=_verify_ctx()
        ) as client:
            resp = await client.post(
                settings.groq_chat_url,
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code != 200:
            logger.error("Contextual Groq error %s: %s", resp.status_code, resp.text[:300])
            return None
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Contextual Groq returned non-JSON.")
        return None
    except Exception as e:  # pragma: no cover - network
        logger.error("Contextual Groq call failed: %s: %s", type(e).__name__, e)
        return None


def _build_pattern(rows, proposal: dict, current: dict) -> ConditionalPattern | None:
    """Verify one proposal against history; return a ConditionalPattern or None."""
    device = proposal.get("device")
    action = (proposal.get("action") or "ON").upper()
    cond = proposal.get("condition") or {}
    if not device or "feature" not in cond or "op" not in cond:
        return None

    verdict = df.verify_conditional(rows, device, action, cond, proposal.get("kind", "auto"))
    if not verdict["supported"] or verdict["confidence"] < _MIN_CONFIDENCE:
        return None

    label = proposal.get("human_label") or f"{device} · {df.humanize_condition(cond)}"
    claim = proposal.get("claim") or f"{device} {action.lower()} {df.humanize_condition(cond)}."
    feat = str(cond.get("feature"))
    pid = f"COND#{device}#{action}#{feat}{cond.get('op')}{cond.get('value')}"
    return ConditionalPattern(
        pattern_id=pid,
        device=device,
        action=action,
        kind=verdict["kind"],
        condition=Condition(feature=cond["feature"], op=cond["op"], value=cond.get("value")),
        human_label=label,
        claim=claim,
        confidence=verdict["confidence"],
        occurrences=verdict["occurrences"],
        evidence=verdict["evidence"],
        active_now=df.condition_active(cond, current),
        source="llm+verified",
    )


def _deterministic_fallback(rows, devices: list[str], current: dict) -> list[ConditionalPattern]:
    """Brute-force a small feature grid so the demo works even if the LLM is down."""
    persons = sorted({p for r in rows for p in r["arrivals"]})
    candidate_conditions = [
        {"feature": "temperature_c", "op": ">", "value": 32},
        {"feature": "is_weekend", "op": "==", "value": True},
        {"feature": "is_weekend", "op": "==", "value": False},
        *[{"feature": f"arrived:{p}", "op": "==", "value": True} for p in persons],
    ]
    found: dict[str, ConditionalPattern] = {}
    for dev in devices:
        for cond in candidate_conditions:
            cp = _build_pattern(rows, {"device": dev, "action": "ON", "condition": cond}, current)
            if cp and (dev not in found or cp.confidence > found[dev].confidence):
                found[dev] = cp
    out = list(found.values())
    for cp in out:
        cp.source = "deterministic-fallback"
    return out


async def generate_contextual_patterns(
    household_id: str,
    events: list[Event],
    base_patterns: list[BasePattern],
    current: dict,
) -> dict:
    """Produce verified conditional patterns. Returns a dict for the API layer."""
    rows = df.build_day_rows(events)
    devices = df.candidate_devices(rows)

    settings = get_settings()
    user_payload = {
        "base_routines": _base_summary(base_patterns),
        "devices": devices,
        "days": df.compact_rows(rows, devices),
    }
    llm = await _call_groq_json(SYSTEM_PROMPT, json.dumps(user_payload), settings)

    proposals = (llm or {}).get("patterns", []) if isinstance(llm, dict) else []
    llm_powered = bool(proposals)

    verified: dict[str, ConditionalPattern] = {}
    for prop in proposals:
        cp = _build_pattern(rows, prop, current)
        if cp:
            verified[cp.pattern_id] = cp  # dedupe by id

    # If the LLM produced nothing usable, fall back to the deterministic scan so
    # the feature always demonstrates something.
    if not verified:
        for cp in _deterministic_fallback(rows, devices, current):
            verified[cp.pattern_id] = cp
        llm_powered = False

    patterns = sorted(verified.values(), key=lambda p: p.confidence, reverse=True)
    return {
        "household_id": household_id,
        "generated": len(proposals),
        "verified": len(patterns),
        "llm_powered": llm_powered,
        "base_pattern_count": len(base_patterns),
        "current_context": current,
        "patterns": patterns,
    }