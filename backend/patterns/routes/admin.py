"""Admin / demo endpoints.

These exist purely to make live demos easy: seed a household with 30 days of
synthetic history (+ today's anomalies) and extract patterns in one call, so the
frontend's "Load Demo Data" button gives judges an instantly populated home.

Not part of the core platform contract — safe to omit in a real deployment.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from patterns.logic import event_service, pattern_service, state_service
from patterns.models.state import HouseholdState

router = APIRouter(prefix="/admin", tags=["admin"])

# scenario key -> (household_id, generator callable)
_SCENARIOS = {
    "H001": "son_departure",
    "H002": "ac_motor_light",
    "H003": "indian_context_care",
    "H004": "context_conditional",
}


def _generate(household_id: str):
    if household_id == "H001":
        from patterns.tests.sample_data import generate

        return generate(days=30, include_today_anomaly=True)
    if household_id == "H002":
        from patterns.tests.sample_data_h002 import generate

        return generate(days=30)
    if household_id == "H003":
        from patterns.tests.sample_data_h003 import generate

        return generate(days=30)
    if household_id == "H004":
        from patterns.tests.sample_data_h004 import generate

        return generate(days=30)
    raise HTTPException(status_code=404, detail=f"Unknown scenario: {household_id}")


@router.post("/seed/{household_id}")
def seed(household_id: str) -> dict:
    """Seed one household with history, rebuild state, and extract patterns.

    Idempotent: clears any existing events for the household first, so running
    the demo seed repeatedly never accumulates duplicate events.
    """
    removed = event_service.delete_household_events(household_id)
    payloads = _generate(household_id)
    stored = event_service.store_events(payloads)

    # Rebuild the live snapshot from scratch so stale device states don't linger.
    fresh = HouseholdState.empty(household_id)
    state_service.save_state(fresh)
    for ev in event_service.get_recent_events(household_id, 3):
        state_service.apply_event(ev)

    patterns = pattern_service.extract_and_store(household_id)
    return {
        "household_id": household_id,
        "scenario": _SCENARIOS.get(household_id),
        "events_cleared": removed,
        "events_stored": len(stored),
        "patterns_extracted": len(patterns),
    }


@router.get("/scenarios")
def scenarios() -> dict:
    return {"scenarios": _SCENARIOS}
