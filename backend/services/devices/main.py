"""Device Control / Ambient Intelligence Microservice.

Two responsibilities:

  1. (Legacy) Map a mood + cognitive load to a single-room environment preset.
     Kept for backward-compatibility with the older flow.

  2. (Ambient Intelligence) The ARBITER for the fixed H003 care home: take the
     three observation sources — PATTERN (learned routine), MOOD (reactive
     comfort) and SAFETY (protective override) — plus any MANUAL human overrides,
     and resolve a single coherent directive per room using a deterministic
     priority ladder. Nothing is persisted; every call is ephemeral, so the demo
     data is never mutated no matter how much the home is poked at.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI
from pydantic import BaseModel

from services.devices.controller import (
    device_controller,
    MoodState,
    CognitiveLoad,
    EnvironmentState,
    MOOD_PRESETS,
)
from services.devices import arbiter, scenario

app = FastAPI(title="MoodSense — Device Control & Ambient Intelligence")


# ─── Legacy mood→environment endpoints ───────────────────────────────────────

class EnvironmentRequest(BaseModel):
    mood: MoodState
    cognitive_load: CognitiveLoad
    user_id: str = "default"
    room_id: str = "living-room"


class DeviceCommandResponse(BaseModel):
    environment: EnvironmentState
    commands_sent: list[dict] = []
    room_id: str


@app.get("/health")
def health():
    return {"service": "device-control", "status": "ok"}


@app.post("/adjust", response_model=DeviceCommandResponse)
async def adjust_environment(request: EnvironmentRequest):
    """Compute and apply environment adjustments based on mood + cognitive load."""
    env = device_controller.compute_environment(
        mood=request.mood,
        cognitive_load=request.cognitive_load,
    )
    commands = _build_device_commands(env, request.room_id)
    return DeviceCommandResponse(
        environment=env,
        commands_sent=commands,
        room_id=request.room_id,
    )


@app.get("/presets")
async def get_presets():
    """Return all available mood presets for reference."""
    return {mood.value: preset for mood, preset in MOOD_PRESETS.items()}


# ─── Ambient Intelligence (H003 arbiter) ─────────────────────────────────────

class ArbitrateRequest(BaseModel):
    # Demo clock — drives the PATTERN routine schedule.
    time: str | None = None
    # Active reactive signals (0 or 1 each) — see GET /devices/scenario.
    mood: str | None = None
    safety: str | None = None
    # Device-level human overrides {device_id: on/off}. Any room with an entry
    # is handed to MANUAL until the frontend's override timer drops it.
    manual: dict[str, bool] = {}


@app.get("/scenario")
async def get_scenario():
    """The fixed H003 demo script: sources, signals, routines, guided beats."""
    return scenario.scenario_payload()


@app.post("/arbitrate")
async def arbitrate_house(request: ArbitrateRequest):
    """Resolve the whole H003 house for one moment — the heart of the page.

    Deterministic: the same {time, mood, safety, manual} always yields the same
    per-room decision, so the demo is fully explainable end-to-end.
    """
    return arbiter.arbitrate(
        time=request.time,
        mood=request.mood,
        safety=request.safety,
        manual=request.manual,
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _build_device_commands(env: EnvironmentState, room_id: str) -> list[dict]:
    """Translate environment state into IoT device commands."""
    commands = []
    commands.append({
        "device_type": "light",
        "room_id": room_id,
        "action": "set",
        "params": {
            "color": env.light_color,
            "brightness": env.light_brightness,
            "temperature_k": env.light_temperature_k,
        },
    })
    if env.music_genre:
        commands.append({
            "device_type": "speaker",
            "room_id": room_id,
            "action": "play",
            "params": {
                "genre": env.music_genre,
                "volume": env.music_volume,
            },
        })
    commands.append({
        "device_type": "notification_hub",
        "room_id": room_id,
        "action": "set_mode",
        "params": {
            "mode": env.notification_mode,
        },
    })
    return commands
