"""Merge learned patterns + the active occasion overlay into one annotated
daily routine — the "adapted routine" the UI shows after applying a context note.

The base patterns are read-only ground truth; adjustments are applied on top and
each affected line is tagged (shifted / added / suppressed / tweaked) with the
reason, so the change is visible and explainable. Nothing here mutates anything.
"""
from __future__ import annotations

from datetime import datetime, timezone

from patterns.logic import adjustment_service, pattern_service
from patterns.models.context_note import EffectiveSchedule, ScheduleEntry
from patterns.models.patterns import DurationPattern, SequencePattern, TimePattern


def _time_of(p) -> str | None:
    if isinstance(p, TimePattern):
        return p.usual_time
    if isinstance(p, SequencePattern):
        return p.usual_time
    if isinstance(p, DurationPattern):
        return p.usual_start_time
    return None


def _label_of(p) -> str:
    if isinstance(p, TimePattern):
        return f"{p.device} {p.action}"
    if isinstance(p, SequencePattern):
        return p.description
    if isinstance(p, DurationPattern):
        return f"{p.device} runs ~{p.usual_duration_minutes:.0f} min"
    return p.pattern_id


def _sort_key(e: ScheduleEntry) -> tuple:
    # Timed entries first (by time); untimed (suppressed/added-without-time) last.
    if e.time and ":" in e.time:
        h, m = e.time.split(":")[:2]
        try:
            return (0, int(h) * 60 + int(m))
        except ValueError:
            pass
    return (1, 0)


def build(household_id: str) -> EffectiveSchedule:
    patterns = pattern_service.get_patterns(household_id)
    adjustments = adjustment_service.list_active(household_id)

    by_target: dict[str, list] = {}
    adds: list = []
    for a in adjustments:
        if a.type == "add" or not a.target_pattern_id:
            adds.append(a)
        else:
            by_target.setdefault(a.target_pattern_id, []).append(a)

    entries: list[ScheduleEntry] = []
    for p in patterns:
        t = _time_of(p)
        adjs = by_target.get(p.pattern_id, [])
        if t is None and not adjs:
            continue  # not part of the daily schedule and untouched → skip

        entry = ScheduleEntry(
            time=t,
            label=_label_of(p),
            device=getattr(p, "device", None),
            action=getattr(p, "action", None),
            status="normal",
            pattern_id=p.pattern_id,
        )
        for a in adjs:
            if a.type == "shift" and a.new_time:
                entry.old_time, entry.time, entry.status = entry.time, a.new_time, "shifted"
            elif a.type == "suppress":
                entry.status = "suppressed"
            elif a.type == "adjust":
                entry.status = "tweaked"
                entry.note = a.description
            entry.reason = a.reason or a.description
            entry.occasion = a.occasion
        entries.append(entry)

    for a in adds:
        entries.append(ScheduleEntry(
            time=a.new_time,
            label=(f"{a.device} {a.action or 'ON'}" if a.device else a.description),
            device=a.device,
            action=a.action,
            status="added",
            note=a.description,
            reason=a.reason or a.description,
            occasion=a.occasion,
        ))

    entries.sort(key=_sort_key)
    occasions = sorted({a.occasion for a in adjustments if a.occasion})
    adjusted = sum(1 for e in entries if e.status != "normal")
    return EffectiveSchedule(
        household_id=household_id,
        date=datetime.now(timezone.utc).date().isoformat(),
        occasions=occasions,
        adjusted_count=adjusted,
        entries=entries,
    )
