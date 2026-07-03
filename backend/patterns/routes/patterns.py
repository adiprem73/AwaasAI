"""Pattern API: trigger extraction + read learned patterns."""
from __future__ import annotations

from fastapi import APIRouter

from patterns.app.config import get_settings
from patterns.logic import (
    day_features,
    event_service,
    pattern_intelligence,
    pattern_service,
)
from patterns.models.contextual import ContextualRequest, ContextualResponse

router = APIRouter(prefix="/patterns", tags=["patterns"])


@router.post("/{household_id}/extract")
def extract(household_id: str) -> dict:
    """Manually run the deterministic extraction job (also runs automatically
    on a fixed interval via the in-process scheduler)."""
    patterns = pattern_service.extract_and_store(household_id)
    return {
        "household_id": household_id,
        "extracted": len(patterns),
        "patterns": [p.model_dump(mode="json") for p in patterns],
    }


@router.get("/{household_id}")
def list_patterns(household_id: str) -> dict:
    patterns = pattern_service.get_patterns(household_id)
    return {
        "household_id": household_id,
        "count": len(patterns),
        "patterns": [p.model_dump(mode="json") for p in patterns],
    }


@router.post("/{household_id}/contextual", response_model=ContextualResponse)
async def contextual_patterns(
    household_id: str, body: ContextualRequest | None = None
) -> ContextualResponse:
    """LLM-generated, deterministically-verified *conditional* patterns.

    The deterministic engine only mines unconditional routines. This endpoint
    asks the LLM to propose routines that depend on a condition (temperature,
    weekday, who's home), then re-measures every proposal against real history
    (:mod:`patterns.logic.day_features`) so only rules the data backs are
    returned. ``body`` supplies the live house context so the response can flag
    which conditional patterns apply *right now*.
    """
    body = body or ContextualRequest()
    settings = get_settings()
    events = event_service.get_recent_events(household_id, settings.analysis_window_days)
    base = pattern_service.get_patterns(household_id)
    current = day_features.now_context(
        temperature_c=body.temperature_c,
        is_weekend=body.is_weekend,
        occupants=body.occupants,
        at=body.at,
    )
    result = await pattern_intelligence.generate_contextual_patterns(
        household_id, events, base, current
    )
    return ContextualResponse(**result)
