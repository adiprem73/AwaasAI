"""Context-note API — user tells the home about an occasion; it adapts routines.

    voice/text → transcript → LLM plan (preview) → user confirms → overlay applied

The plan is a set of TEMPORARY adjustments that overlay the learned patterns
without mutating them. Everything is reversible.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from patterns.logic import adjustment_service, context_planner, schedule_view
from patterns.models.context_note import (
    ApplyRequest,
    ContextNoteRequest,
    ContextPlan,
    EffectiveSchedule,
    StoredAdjustment,
)

router = APIRouter(prefix="/context", tags=["context-notes"])


@router.post("/{household_id}/note", response_model=ContextPlan)
async def make_plan(household_id: str, body: ContextNoteRequest) -> ContextPlan:
    """Transcribe (if audio) + turn the note into a previewable adjustment plan.

    Nothing is persisted here — the frontend shows the plan and the user confirms
    with ``/note/apply``.
    """
    text = (body.text or "").strip()
    if not text and body.audio_base64:
        text = await context_planner.transcribe(body.audio_base64, body.audio_format or "webm")
    if not text:
        raise HTTPException(status_code=400, detail="No note text (or couldn't transcribe audio).")

    plan = await context_planner.plan(household_id, text)
    return ContextPlan(**plan)


@router.post("/{household_id}/note/apply", response_model=list[StoredAdjustment])
def apply_plan(household_id: str, body: ApplyRequest) -> list[StoredAdjustment]:
    """Persist a confirmed (possibly user-edited) plan as an overlay."""
    if not body.adjustments:
        raise HTTPException(status_code=400, detail="No adjustments to apply.")
    return adjustment_service.add_many(
        household_id, body.adjustments,
        occasion=body.occasion, occasion_date=body.occasion_date,
    )


@router.get("/{household_id}/effective-schedule", response_model=EffectiveSchedule)
def effective_schedule(household_id: str) -> EffectiveSchedule:
    """The daily routine with the active occasion overlay applied — each line
    tagged shifted / added / suppressed / tweaked so the changes are visible."""
    return schedule_view.build(household_id)


@router.get("/{household_id}/adjustments", response_model=list[StoredAdjustment])
def list_adjustments(household_id: str, upcoming_only: bool = False) -> list[StoredAdjustment]:
    """Active overlay adjustments for the home."""
    today = datetime.now(timezone.utc).date().isoformat() if upcoming_only else None
    return adjustment_service.list_active(household_id, on_or_after=today)


@router.delete("/{household_id}/adjustments/{adjustment_id}")
def delete_adjustment(household_id: str, adjustment_id: str) -> dict:
    adjustment_service.delete(household_id, adjustment_id)
    return {"deleted": adjustment_id}


@router.delete("/{household_id}/adjustments")
def clear_adjustments(household_id: str) -> dict:
    return {"cleared": adjustment_service.clear(household_id)}
