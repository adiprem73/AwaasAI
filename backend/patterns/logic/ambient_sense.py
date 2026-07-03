"""Sense-making for ambient sounds — turns a detected sound into an INSIGHT.

A raw sound event ("cooker whistled") is not interesting; the insight is whether
it *deviates from what's normal for that sound*. Each sound declares a
:class:`~patterns.logic.ambient_sounds.Sense` strategy; this module evaluates it
DETERMINISTICALLY against the sound's own logged history:

  * ``instant``  — flag always (smoke alarm, glass break).
  * ``rate``     — learn a per-window COUNT baseline; flag over-frequency
                   (cooker whistling far more than usual → forgotten on flame).
  * ``burst``    — flag K occurrences within N minutes (repeated coughing).
  * ``surface``  — flag every occurrence; severity scales with recent frequency
                   (baby crying — the LLM narrates the nuance).

Returns a plain dict the route attaches to the interpretation and (when flagged)
hands to the LLM narrator. Deterministic decides WHETHER it's abnormal; the LLM
only decides HOW to say it.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from patterns.logic import event_service
from patterns.logic.ambient_sounds import ambient_device_id, get_sound

_NONE = {
    "flagged": False, "strategy": "none", "reason": "", "severity": None,
    "evidence": {}, "always_narrate": False,
}


def _sound_events(household_id: str, key: str, days: int = 35) -> list:
    dev = ambient_device_id(key)
    return [
        e for e in event_service.get_recent_events(household_id, days)
        if e.device_id == dev
    ]


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _window_for(hour: int, windows: tuple) -> tuple | None:
    for w in windows:
        if w[0] <= hour < w[1]:
            return w
    return None


def evaluate(household_id: str, key: str, clock: datetime) -> dict:
    """Evaluate the sense-making strategy for a just-detected sound.

    ``clock`` is the (possibly simulated) 'now'. Call this AFTER the current event
    is logged so counts include it.
    """
    sound = get_sound(key)
    sense = getattr(sound, "sense", None) if sound else None
    if not sense:
        return dict(_NONE)

    now = _utc(clock)
    strat = sense.strategy

    # ── instant: intrinsically significant ───────────────────────────────────
    if strat == "instant":
        return {
            "flagged": True, "strategy": "instant",
            "reason": f"{sound.label} — inherently urgent, no pattern needed.",
            "severity": sound.severity, "evidence": {}, "always_narrate": True,
        }

    events = _sound_events(household_id, key)

    # ── burst: K occurrences within N minutes ────────────────────────────────
    if strat == "burst":
        cutoff = now - timedelta(minutes=sense.burst_minutes)
        recent = [e for e in events if cutoff <= _utc(e.timestamp) <= now]
        n = len(recent)
        flagged = n >= sense.burst_count
        return {
            "flagged": flagged, "strategy": "burst",
            "reason": (f"{n} times in {sense.burst_minutes} min — looks persistent."
                       if flagged else ""),
            "severity": "warn" if flagged else None,
            "evidence": {"recent_count": n, "window_minutes": sense.burst_minutes,
                         "threshold": sense.burst_count},
            "always_narrate": flagged,
        }

    # ── surface: narrate EVERY occurrence; severity scales with recent
    #    frequency (no schedule — a baby has no fixed time, so a single cry is a
    #    gentle FYI while repeated cries are a real concern). ─────────────────
    if strat == "surface":
        cutoff = now - timedelta(minutes=sense.burst_minutes)
        recent = [e for e in events if cutoff <= _utc(e.timestamp) <= now]
        today = [e for e in events if _utc(e.timestamp).date() == now.date()]
        n = len(recent)
        if n >= sense.burst_count:
            sev, reason = "warn", f"{n} times in {sense.burst_minutes} min — more than usual."
        elif n >= 2:
            sev, reason = "suggest", f"{n} times in {sense.burst_minutes} min."
        else:
            sev, reason = "info", "just the once — probably fine."
        return {
            # Repeated → a real "flag"; a single cry is surfaced (narrated) but not
            # flagged as a concern.
            "flagged": n >= 2, "strategy": "surface", "reason": reason, "severity": sev,
            "evidence": {"recent_count": n, "today_total": len(today),
                         "window_minutes": sense.burst_minutes},
            "always_narrate": True,
        }

    # ── rate: today's count in the window vs a learned baseline ──────────────
    if strat == "rate":
        win = _window_for(now.hour, sense.windows)
        if win is None:
            return {
                "flagged": True, "strategy": "rate",
                "reason": f"{sound.label} at an unusual hour "
                          f"({now.hour:02d}:{now.minute:02d}).",
                "severity": "warn",
                "evidence": {"off_window": True}, "always_narrate": True,
            }
        a, b = win
        per_day: dict = defaultdict(int)
        for e in events:
            ts = _utc(e.timestamp)
            if a <= ts.hour < b:
                per_day[ts.date()] += 1
        today_count = per_day.get(now.date(), 0)
        past = [c for d, c in per_day.items() if d != now.date()]
        window_str = f"{a:02d}:00–{b:02d}:00"
        if len(past) < sense.min_days:
            return {
                "flagged": False, "strategy": "rate", "reason": "",
                "severity": None,
                "evidence": {"today_count": today_count, "window": window_str,
                             "baseline_days": len(past)},
                "always_narrate": False,
            }
        mean = statistics.mean(past)
        std = statistics.pstdev(past) if len(past) > 1 else 0.0
        threshold = max(round(mean + 2 * std), round(mean) + sense.baseline_extra)
        flagged = today_count >= threshold and today_count > mean
        return {
            "flagged": flagged, "strategy": "rate",
            "reason": (f"{today_count} in the {window_str} window vs the usual "
                       f"~{round(mean)}." if flagged else ""),
            "severity": "warn" if flagged else None,
            "evidence": {"today_count": today_count, "usual_mean": round(mean, 1),
                         "threshold": threshold, "window": window_str},
            "always_narrate": flagged,
        }

    return dict(_NONE)
