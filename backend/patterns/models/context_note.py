"""Models for user-driven context notes → temporary pattern adjustments.

The user tells the home about a one-off occasion by voice or text ("guests are
coming tomorrow", "tomorrow is Diwali"). An LLM turns that into a small set of
*temporary, dated adjustments* that overlay the learned patterns without changing
them. The user previews and confirms before anything is applied.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ContextNoteRequest(BaseModel):
    """A spoken or typed note about an upcoming occasion."""

    text: str | None = Field(None, description="Typed note (or omit and send audio).")
    audio_base64: str | None = Field(None, description="Recorded mic clip (Groq Whisper handles webm).")
    audio_format: str = Field("webm", examples=["webm", "wav", "mp3"])


ADJUSTMENT_TYPES = ("add", "shift", "suppress", "adjust")


class ProposedAdjustment(BaseModel):
    """One temporary change the LLM proposes for the occasion."""

    type: str = Field(..., description="add | shift | suppress | adjust")
    target_pattern_id: str | None = Field(
        None, description="Existing pattern this modifies (required for shift/suppress/adjust)."
    )
    device: str | None = Field(None, examples=["decoration_lights"])
    action: str | None = Field(None, examples=["ON", "OFF"])
    new_time: str | None = Field(None, description="HH:MM for `shift`/`add`.")
    description: str = Field(..., description="Human sentence describing the change.")
    reason: str = Field("", description="Why — tied to the occasion.")


class ContextPlan(BaseModel):
    """The previewed plan returned before the user applies it."""

    household_id: str
    transcript: str = ""
    occasion: str = Field("", examples=["guests", "diwali", "party", "travel", "illness"])
    occasion_date: str = Field("", description="ISO date the plan applies to.")
    summary: str = ""
    adjustments: list[ProposedAdjustment] = Field(default_factory=list)
    llm_powered: bool = True


class ApplyRequest(BaseModel):
    """Confirm a (possibly user-edited) plan to persist it as an overlay."""

    transcript: str = ""
    occasion: str = ""
    occasion_date: str = ""
    summary: str = ""
    adjustments: list[ProposedAdjustment] = Field(default_factory=list)


class StoredAdjustment(ProposedAdjustment):
    """A persisted overlay adjustment."""

    id: str
    household_id: str
    occasion: str = ""
    occasion_date: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ScheduleEntry(BaseModel):
    """One line of the (possibly adapted) daily routine."""

    time: str | None = None          # HH:MM (None → no fixed time)
    label: str = ""                  # human line, e.g. "pooja_lamp ON"
    device: str | None = None
    action: str | None = None
    status: str = "normal"           # normal | shifted | added | suppressed | tweaked
    old_time: str | None = None      # for `shifted`
    note: str = ""                   # extra detail (tweak text / add description)
    reason: str = ""                 # why it changed (occasion)
    occasion: str = ""
    pattern_id: str | None = None


class EffectiveSchedule(BaseModel):
    """The daily routine with the active occasion overlay applied."""

    household_id: str
    date: str = ""
    occasions: list[str] = Field(default_factory=list)
    adjusted_count: int = 0
    entries: list[ScheduleEntry] = Field(default_factory=list)
