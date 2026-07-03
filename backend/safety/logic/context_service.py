"""Context service: orchestrate state + patterns + recent events -> context.

Thin coordination layer the API/Lambda call to produce the final
:class:`ContextObject` that will be sent to Bedrock in a future phase.
"""
from __future__ import annotations

from datetime import datetime, timezone

from safety.context_builder import build_context
from safety.models.context import ContextObject
from safety.models.events import DeviceAction, DeviceType, Event
from safety.models.patterns import TimePattern
from safety.models.safety import PersonProfile
from safety.models.state import HouseholdState
from safety.logic import event_service, pattern_service, profile_service, state_service

# Recent-event tail window (days) for short-term memory in the context.
RECENT_WINDOW_DAYS = 1

# Actions that represent a routine being *completed* / *happening*.
_ROUTINE_ACTIVATIONS = {"ON", "OPEN", "ARRIVE", "ACTIVE", "TAKEN"}


def _healthy_completions(
    household_id: str,
    patterns: list,
    now: datetime,
    skip: set[str],
) -> list[Event]:
    """Synthetic "on-track" events: for every learned activation routine whose
    usual time has already passed today, emit a completion event — UNLESS its
    device is in ``skip`` (a deliberately-missed routine).

    This is what keeps the home CALM by default: without it, the passage of the
    demo clock alone makes every not-yet-injected routine look "missed", raising
    phantom concerns the user never triggered. A routine is only ever flagged
    when the user deliberately omits it (``skip``).
    """
    out: list[Event] = []
    for p in patterns:
        if not isinstance(p, TimePattern) or p.action not in _ROUTINE_ACTIVATIONS:
            continue
        if p.device in skip:
            continue
        try:
            h, m = (int(x) for x in p.usual_time.split(":"))
        except (ValueError, AttributeError):
            continue
        usual = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if usual <= now:
            out.append(Event(
                household_id=household_id,
                device_id=p.device,
                device_type=DeviceType.OTHER,
                room="home",
                action=DeviceAction(p.action),
                triggered_by="baseline",
                timestamp=usual,
            ))
    return out


def generate_context(household_id: str, *, now: datetime | None = None) -> ContextObject:
    state = state_service.get_state(household_id)
    patterns = pattern_service.get_patterns(household_id)
    recent = event_service.get_recent_events(household_id, RECENT_WINDOW_DAYS)
    profiles = profile_service.get_profiles(household_id)
    return build_context(state, patterns, recent, now=now, profiles=profiles)


def evaluate_context(
    household_id: str,
    *,
    active_devices: list[str],
    people_home: dict[str, bool] | None = None,
    device_on_since: dict[str, str] | None = None,
    now: datetime | None = None,
    profiles: list[PersonProfile] | None = None,
    extra_recent: list[Event] | None = None,
    ignore_stored_events: bool = False,
    healthy_baseline: bool = False,
    skip_completions: list[str] | None = None,
) -> ContextObject:
    """Evaluate a *user-supplied* what-if state against the learned patterns.

    This is the "set the state + clock, then hit Go" flow: instead of reading
    the persisted (and possibly stale) household snapshot, the caller passes the
    exact current state — which devices are ON and (optionally) who is home — and
    we compare it against the patterns mined from history to surface anomalies.

    The state is **ephemeral**: nothing is written back to the events table or
    the state table, so repeated evaluations never pollute the demo data.

    Ephemeral cast & signals (powers the live "dollhouse" dashboard):

    * ``profiles`` — when supplied, the vulnerability lens is driven entirely by
      this in-memory cast (who is placed in the home right now) instead of the
      persisted profile table. This lets the UI add/remove people live and watch
      every concern re-escalate, with nothing written to DynamoDB.
    * ``extra_recent`` — synthetic momentary signals (an SOS press, a wearable
      ALERT, a "last seen" ping) appended to the recent-event tail so the
      event-reading detectors (health / SOS / global-inactivity) can fire
      without persisting anything.
    * ``ignore_stored_events`` — drop the stored event tail entirely and judge
      only against ``extra_recent``. Used for a clean "quiet house" inactivity
      demo where seeded routine events would otherwise count as signs of life.
    """
    patterns = pattern_service.get_patterns(household_id)
    state = HouseholdState(
        household_id=household_id,
        active_devices=list(active_devices),
        people_home=people_home or {},
        device_on_since=device_on_since or {},
    )
    # An explicit cast (even an empty list) overrides the persisted profiles so
    # the UI fully owns "who is home"; ``None`` falls back to the stored table.
    if profiles is not None:
        prof = {p.person_id: p for p in profiles}
    else:
        prof = profile_service.get_profiles(household_id)

    # Recent events feed the detectors that read history (global-inactivity,
    # health, SOS, missed-routine). The painted active_devices remain the source
    # of truth for "what is on right now".
    recent = (
        [] if ignore_stored_events
        else event_service.get_recent_events(household_id, RECENT_WINDOW_DAYS)
    )
    recent = list(recent)
    if healthy_baseline:
        # Mark today's routines-so-far as done → the home is calm unless the user
        # deliberately omits one (``skip_completions``).
        eff_now = now or datetime.now(timezone.utc)
        recent += _healthy_completions(
            household_id, patterns, eff_now, set(skip_completions or [])
        )
    if extra_recent:
        recent = recent + list(extra_recent)
    return build_context(state, patterns, recent, now=now, profiles=prof)
