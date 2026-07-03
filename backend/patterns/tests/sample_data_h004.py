"""Synthetic 30-day event generator for household H004 — the CONTEXT-AWARE home.

Unlike H001–H003 (which exercise the *deterministic* extractors), H004 is built
specifically to demonstrate **context-conditional patterns** — routines whose
behaviour depends on an external condition the pure time/duration engine cannot
express. It bakes in three such correlations, each with a matching contextual
signal in the history so an LLM can *discover* the rule and the deterministic
verifier can *confirm* it against real days:

  TC1 · Temperature → AC
        ``living_room_ac`` turns ON in the afternoon ONLY on hot days (>32°C).
        A daily ``weather_sensor`` reading carries the temperature so every day
        (hot or cool) is labelled. The pure time engine sees the AC on only
        ~half the days → too little support to keep, so it *misses* the routine;
        the conditional layer recovers it as "daily, given heat".

  TC2 · Weekend time-shift
        ``porch_light`` turns ON ~19:00 on weekdays but ~20:00 on weekends
        (~1 h later). The multi-cluster time engine keeps only the dominant
        weekday cluster ("porch on ~19:00") and drops the smaller weekend one —
        so the shift is invisible until the conditional layer splits by day type.

  TC3 · Occupancy / commute-conditional
        ``bedroom_ac`` is pre-cooled ~17:45 ONLY on days the mother commutes home
        (a ``mother_presence`` ARRIVE ~18:00). She works most weekdays but the
        signal is deliberately NOT identical to "weekday": she occasionally works
        a weekend and occasionally takes a weekday off, so ``arrived:mother``
        predicts the AC better than ``is_weekend`` — showing the reasoning layer
        can pick the *right* cause.

Plus one purely unconditional baseline (``water_motor`` ~09:00 daily) so the
deterministic engine still finds a normal pattern for contrast.

All randomness is seeded → the history is identical on every run.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from patterns.models.events import DeviceAction, DeviceType, EventCreate

HOUSEHOLD = "H004"
_rng = random.Random(2026)  # dedicated, deterministic RNG


def _at(day: datetime, hour: int, minute: int, jitter: int = 0) -> datetime:
    minute += _rng.randint(-jitter, jitter) if jitter else 0
    base = day.replace(hour=hour, minute=0, second=0, microsecond=0)
    return base + timedelta(minutes=minute)


def _ev(day_ts: datetime, device: str, dtype: DeviceType, room: str,
        action: DeviceAction, by: str, meta: dict | None = None) -> EventCreate:
    return EventCreate(
        household_id=HOUSEHOLD, device_id=device, device_type=dtype, room=room,
        action=action, triggered_by=by, timestamp=day_ts, metadata=meta,
    )


def generate(days: int = 30) -> list[EventCreate]:
    events: list[EventCreate] = []
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    for d in range(days, 0, -1):
        day = today - timedelta(days=d)
        is_weekend = day.weekday() >= 5  # Sat/Sun

        # ── Daily weather reading (labels EVERY day, hot or cool) ────────────
        # Bimodal on purpose so there's a clean gap around the 32°C threshold.
        # Stored as an int: DynamoDB rejects Python floats in event metadata, and
        # whole degrees are plenty precise for the demo.
        hot = _rng.random() < 0.5
        temp_c = _rng.randint(33, 38) if hot else _rng.randint(24, 30)
        events.append(_ev(
            _at(day, 13, 0), "weather_sensor", DeviceType.OTHER, "outdoor",
            DeviceAction.ACTIVE, "system",
            meta={"temperature_c": temp_c, "condition": "hot" if hot else "cool"},
        ))

        # ── Baseline unconditional routine: water motor ~09:00, ~15 min ──────
        motor_on = _at(day, 9, 0, jitter=10)
        events += [
            _ev(motor_on, "water_motor", DeviceType.MOTOR, "utility", DeviceAction.ON, "system"),
            _ev(motor_on + timedelta(minutes=15 + _rng.randint(-2, 2)),
                "water_motor", DeviceType.MOTOR, "utility", DeviceAction.OFF, "system"),
        ]

        # ── TC1 · Temperature → living-room AC (afternoon, hot days only) ────
        if hot:
            ac_on = _at(day, 14, 30, jitter=20)
            events += [
                _ev(ac_on, "living_room_ac", DeviceType.AC, "living_room", DeviceAction.ON, "father"),
                _ev(ac_on + timedelta(minutes=150 + _rng.randint(-20, 20)),
                    "living_room_ac", DeviceType.AC, "living_room", DeviceAction.OFF, "father"),
            ]

        # ── TC2 · Weekend time-shift on the porch light ──────────────────────
        porch_hour = 20 if is_weekend else 19  # ~1 h later on weekends
        porch_on = _at(day, porch_hour, 0, jitter=8)
        events += [
            _ev(porch_on, "porch_light", DeviceType.LIGHT, "porch", DeviceAction.ON, "system"),
            _ev(_at(day, 23, 0, jitter=10),
                "porch_light", DeviceType.LIGHT, "porch", DeviceAction.OFF, "system"),
        ]

        # ── TC3 · Occupancy/commute → bedroom AC pre-cool ────────────────────
        # Mother commutes most weekdays, with a little noise so "arrived:mother"
        # is a *better* predictor than "is_weekend".
        mother_commutes = not is_weekend
        if is_weekend and _rng.random() < 0.18:
            mother_commutes = True            # occasional weekend shift
        if (not is_weekend) and _rng.random() < 0.10:
            mother_commutes = False           # occasional weekday off
        if mother_commutes:
            events.append(_ev(
                _at(day, 18, 0, jitter=10), "mother_presence", DeviceType.PRESENCE,
                "entrance", DeviceAction.ARRIVE, "mother",
            ))
            ac_on = _at(day, 17, 45, jitter=8)  # pre-cool before she's home
            events += [
                _ev(ac_on, "bedroom_ac", DeviceType.AC, "bedroom", DeviceAction.ON, "father"),
                _ev(_at(day, 22, 0, jitter=15),
                    "bedroom_ac", DeviceType.AC, "bedroom", DeviceAction.OFF, "father"),
            ]

    return events