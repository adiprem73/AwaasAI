"""Models for LLM-generated, deterministically-verified *conditional* patterns.

A conditional pattern is a routine that only holds under a condition the pure
statistical engine cannot express — e.g. "the AC runs in the afternoon ONLY when
it's hot". The LLM proposes these; :mod:`patterns.logic.day_features` verifies
each against real history before it is ever returned.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Condition(BaseModel):
    feature: str = Field(..., description="e.g. temperature_c, is_weekend, arrived:mother")
    op: str = Field(..., description="One of > < >= <= == !=")
    value: Any = Field(..., description="Threshold / target (number, bool, or string)")


class ConditionalPattern(BaseModel):
    pattern_id: str
    device: str
    action: str
    kind: str = Field("occurrence", description="occurrence | time_shift")
    condition: Condition
    human_label: str = Field(..., description="Short human name, e.g. 'Hot-day afternoon cooling'")
    claim: str = Field(..., description="One-line plain-English rule")
    confidence: float = Field(ge=0.0, le=1.0)
    occurrences: int = Field(ge=0)
    evidence: dict = Field(default_factory=dict, description="Measured support from real days")
    active_now: bool = False
    source: str = Field("llm+verified", description="How this pattern was produced")


class ContextualRequest(BaseModel):
    """Live house context used to flag which conditional patterns apply RIGHT NOW."""

    temperature_c: float | None = Field(None, examples=[34.0])
    is_weekend: bool | None = Field(None, description="None → derived from today.")
    occupants: list[str] = Field(default_factory=list, examples=[["mother", "father"]])
    at: str | None = Field(None, description="Optional HH:MM simulated clock.")


class ContextualResponse(BaseModel):
    household_id: str
    generated: int = Field(0, description="How many rules the LLM proposed.")
    verified: int = Field(0, description="How many survived deterministic verification.")
    llm_powered: bool = True
    base_pattern_count: int = 0
    current_context: dict = Field(default_factory=dict)
    patterns: list[ConditionalPattern] = Field(default_factory=list)