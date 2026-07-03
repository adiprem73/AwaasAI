"""Context annotation + deterministic verification for conditional patterns.

The deterministic pattern engine mines *unconditional* routines (e.g. "AC on
~14:30"). The contextual layer asks a different question: *does a routine depend
on a condition* (temperature, weekday, who's home)? That needs two things this
module provides, both pure and explainable:

1. **Day annotation** — collapse the raw event stream into one feature row per
   calendar day: weekday/weekend, season, that day's temperature (from the
   ``weather_sensor`` reading), who arrived / was active, and which devices did
   what and when. This is the evidence table an LLM reasons over.

2. **Condition verification** — given a proposed rule "(device, action) depends
   on <condition>", split the days by the condition and MEASURE the effect
   against real history (how often the behaviour happens with vs without the
   condition, and whether its timing shifts). An LLM may *propose* a rule, but a
   rule only survives if the numbers here back it — the ground-truth guardrail.
"""
from __future__ import annotations

from datetime import datetime, timezone

from patterns.models.events import Event

# Features a condition may reference. `arrived:<person>` / `active:<person>` are
# dynamic (any person id after the colon).
STATIC_FEATURES = {"temperature_c", "is_weekend", "dow", "season"}
_OPS = {">", "<", ">=", "<=", "==", "!="}
_DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _season(month: int) -> str:
    # India-ish coarse seasons — enough for demo reasoning.
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "summer"
    if month in (6, 7, 8, 9):
        return "monsoon"
    return "autumn"


def _minutes(ts: datetime) -> int:
    return ts.hour * 60 + ts.minute


# ─── 1 · Day annotation ──────────────────────────────────────────────────────


def build_day_rows(events: list[Event]) -> list[dict]:
    """Collapse events into one feature row per calendar day (UTC), sorted."""
    by_day: dict[str, dict] = {}
    for e in events:
        ts = e.timestamp.astimezone(timezone.utc)
        key = ts.date().isoformat()
        row = by_day.get(key)
        if row is None:
            row = {
                "date": key,
                "dow": _DOW[ts.weekday()],
                "is_weekend": ts.weekday() >= 5,
                "season": _season(ts.month),
                "temperature_c": None,
                "arrivals": set(),
                "actors": set(),
                "activations": {},   # device -> list of {"action","minute"}
            }
            by_day[key] = row

        action = e.action.value
        # Weather reading → the day's temperature label.
        if e.device_id == "weather_sensor":
            temp = (e.metadata or {}).get("temperature_c")
            if temp is not None:
                row["temperature_c"] = float(temp)
            continue

        if e.triggered_by and e.triggered_by != "system":
            row["actors"].add(e.triggered_by)
        if action == "ARRIVE" and e.triggered_by:
            row["arrivals"].add(e.triggered_by)

        row["activations"].setdefault(e.device_id, []).append(
            {"action": action, "minute": _minutes(ts)}
        )

    rows = sorted(by_day.values(), key=lambda r: r["date"])
    # Freeze sets to sorted lists for JSON friendliness.
    for r in rows:
        r["arrivals"] = sorted(r["arrivals"])
        r["actors"] = sorted(r["actors"])
    return rows


def compact_rows(rows: list[dict], devices: list[str]) -> list[dict]:
    """A token-light view for the LLM: per day, the context + first activation
    time (HH:MM) of each candidate device (or null)."""
    out = []
    for r in rows:
        day = {
            "date": r["date"],
            "dow": r["dow"],
            "is_weekend": r["is_weekend"],
            "temperature_c": r["temperature_c"],
            "arrivals": r["arrivals"],
        }
        for dev in devices:
            m = _first_on_minute(r, dev)
            day[dev] = f"{m // 60:02d}:{m % 60:02d}" if m is not None else None
        out.append(day)
    return out


def candidate_devices(rows: list[dict]) -> list[str]:
    devs = set()
    for r in rows:
        devs.update(r["activations"].keys())
    devs.discard("weather_sensor")
    return sorted(devs)


# ─── 2 · Condition evaluation ────────────────────────────────────────────────


def _feature_value(row: dict, feature: str):
    """Resolve a feature to a comparable value for ``row`` (None = unknown)."""
    if feature in STATIC_FEATURES:
        return row.get(feature)
    if feature.startswith("arrived:"):
        return feature.split(":", 1)[1] in row.get("arrivals", [])
    if feature.startswith("active:"):
        return feature.split(":", 1)[1] in row.get("actors", [])
    return None


def _coerce(value, ref):
    """Coerce a JSON condition value toward the type of the resolved feature."""
    if isinstance(ref, bool):
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes"}
        return bool(value)
    if isinstance(ref, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return value


def evaluate_condition(row: dict, condition: dict) -> bool | None:
    """True/False if the condition holds for ``row``; None if indeterminate."""
    feature = condition.get("feature")
    op = condition.get("op")
    value = condition.get("value")
    if feature is None or op not in _OPS:
        return None
    lhs = _feature_value(row, feature)
    if lhs is None:
        return None
    rhs = _coerce(value, lhs)
    if rhs is None:
        return None
    try:
        if op == "==":
            return lhs == rhs
        if op == "!=":
            return lhs != rhs
        if op == ">":
            return lhs > rhs
        if op == "<":
            return lhs < rhs
        if op == ">=":
            return lhs >= rhs
        if op == "<=":
            return lhs <= rhs
    except TypeError:
        return None
    return None


def _first_on_minute(row: dict, device: str) -> int | None:
    """Earliest activation minute (ON/OPEN/ARRIVE/ACTIVE) of a device that day."""
    acts = row.get("activations", {}).get(device, [])
    on = [a["minute"] for a in acts if a["action"] in {"ON", "OPEN", "ARRIVE", "ACTIVE"}]
    return min(on) if on else None


# ─── 3 · Verification (the ground-truth guardrail) ───────────────────────────


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def verify_conditional(
    rows: list[dict],
    device: str,
    action: str,
    condition: dict,
    kind: str = "auto",
) -> dict:
    """Measure a proposed rule against real days. Returns a verdict dict.

    ``kind``: "occurrence" (does it happen at all under the condition),
    "time_shift" (does its usual time move), or "auto" (pick whichever the data
    supports more strongly).
    """
    action = action.upper()
    group_true: list[dict] = []
    group_false: list[dict] = []
    for r in rows:
        verdict = evaluate_condition(r, condition)
        if verdict is True:
            group_true.append(r)
        elif verdict is False:
            group_false.append(r)
        # None → day excluded (feature unknown)

    def _did(r):
        return any(a["action"] == action for a in r.get("activations", {}).get(device, []))

    def _on_min(r):
        return _first_on_minute(r, device)

    nt, nf = len(group_true), len(group_false)
    did_t = [r for r in group_true if _did(r)]
    did_f = [r for r in group_false if _did(r)]
    rate_t = len(did_t) / nt if nt else 0.0
    rate_f = len(did_f) / nf if nf else 0.0

    times_t = [_on_min(r) for r in did_t if _on_min(r) is not None]
    times_f = [_on_min(r) for r in did_f if _on_min(r) is not None]
    mean_t, mean_f = _mean(times_t), _mean(times_f)
    delta_min = abs(mean_t - mean_f)

    # Score each interpretation.
    occ_conf = round(rate_t * (1.0 - rate_f), 3)
    occ_ok = nt >= 3 and nf >= 3 and rate_t >= 0.7 and rate_f <= 0.35

    spread = (_std(times_t) + _std(times_f)) / 2
    shift_conf = round(min(1.0, delta_min / 60.0) * max(0.0, 1.0 - spread / 60.0), 3)
    shift_ok = len(times_t) >= 3 and len(times_f) >= 3 and delta_min >= 25 and spread <= 45

    if kind == "occurrence":
        chosen, ok, conf = "occurrence", occ_ok, occ_conf
    elif kind == "time_shift":
        chosen, ok, conf = "time_shift", shift_ok, shift_conf
    else:  # auto
        if occ_ok and occ_conf >= shift_conf:
            chosen, ok, conf = "occurrence", True, occ_conf
        elif shift_ok:
            chosen, ok, conf = "time_shift", True, shift_conf
        else:
            chosen, ok, conf = ("occurrence", occ_ok, occ_conf) if occ_conf >= shift_conf \
                else ("time_shift", shift_ok, shift_conf)

    occurrences = len(did_t)

    def _hhmm(m: float) -> str:
        m = int(round(m))
        return f"{m // 60:02d}:{m % 60:02d}"

    evidence = {
        "kind": chosen,
        "days_condition_true": nt,
        "days_condition_false": nf,
        "rate_when_true": round(rate_t, 2),
        "rate_when_false": round(rate_f, 2),
        "usual_time_when_true": _hhmm(mean_t) if times_t else None,
        "usual_time_when_false": _hhmm(mean_f) if times_f else None,
        "time_shift_minutes": int(round(delta_min)) if (times_t and times_f) else None,
    }
    return {
        "supported": bool(ok),
        "kind": chosen,
        "confidence": conf,
        "occurrences": occurrences,
        "evidence": evidence,
    }


def condition_active(condition: dict, current: dict) -> bool:
    """Is the condition satisfied by the live house context RIGHT NOW?"""
    row = {
        "temperature_c": current.get("temperature_c"),
        "is_weekend": current.get("is_weekend"),
        "dow": current.get("dow"),
        "season": current.get("season"),
        "arrivals": current.get("occupants", []),
        "actors": current.get("occupants", []),
    }
    return evaluate_condition(row, condition) is True


def now_context(
    *,
    temperature_c: float | None = None,
    is_weekend: bool | None = None,
    occupants: list[str] | None = None,
    at: str | None = None,
    now: datetime | None = None,
) -> dict:
    """Assemble the live-house context used to flag "active now" conditionals."""
    now = now or datetime.now(timezone.utc)
    return {
        "temperature_c": temperature_c,
        "is_weekend": (now.weekday() >= 5) if is_weekend is None else is_weekend,
        "dow": _DOW[now.weekday()],
        "season": _season(now.month),
        "occupants": occupants or [],
        "at": at,
    }


def humanize_condition(condition: dict) -> str:
    """A short human phrase for a condition (UI badge / fallback labels)."""
    f, op, v = condition.get("feature"), condition.get("op"), condition.get("value")
    if f == "temperature_c":
        return f"temperature {op} {v}°C"
    if f == "is_weekend":
        return "on weekends" if str(v).lower() in {"true", "1"} else "on weekdays"
    if f == "season":
        return f"in {v}"
    if f == "dow":
        return f"on {v}"
    if isinstance(f, str) and f.startswith("arrived:"):
        return f"when {f.split(':', 1)[1]} comes home"
    if isinstance(f, str) and f.startswith("active:"):
        return f"when {f.split(':', 1)[1]} is home"
    return f"{f} {op} {v}"