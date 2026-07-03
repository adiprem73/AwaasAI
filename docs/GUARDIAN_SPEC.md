# The Guardian — Adaptive Safety, Feature Spec

> Status: **spec for review** (build after sign-off).
> Decisions locked: cover **all four vulnerable-alone situations** (elderly, woman,
> child, pregnant/unwell); presence via **simulated WiFi/phone**; the Guardian is
> **proactive** — it acts like another person in the home, not just an alarm.

---

## 0 · The idea, in one line
> Turn the existing vulnerability-aware *detector* into a **Guardian**: a presence
> that always knows **who is home**, notices when a **vulnerable person is alone**,
> and then **watches over and protects them** — securing the home, screening
> visitors, checking in, and calling family — the way another adult in the house
> would.

**Philosophy (unchanged):** deterministic engine establishes *ground truth* (who's
home, what's happening, the safety score); the **LLM decides the protective
response and speaks it** like a caring guardian. The LLM can *raise* concern and
choose actions, but it can never *suppress* a real deterministic emergency, and
every action it takes targets a **real device** (resolve-or-drop).

---

## 1 · What exists vs. what's new (build ON the current `safety` service)

**Already there** ([`backend/safety/`](../backend/safety/), port 8006):
- Vulnerability profiles & weights ([`models/safety.py`](../backend/safety/models/safety.py)): elderly/child/pregnant/unwell/normal.
- The **safety overlay** ([`context_builder/safety_overlay.py`](../backend/safety/context_builder/safety_overlay.py)): `vulnerable_alone`, severity escalation, 0–100 score + status.
- Detectors ([`context_builder/anomaly.py`](../backend/safety/context_builder/anomaly.py)): `unsafe_at_night`, `unexpected_activity`, `global_inactivity`, `health_alert`/`sos`, missed-routine.
- The what-if evaluate flow ([`logic/context_service.py`](../backend/safety/logic/context_service.py) `evaluate_context`) + the caring narrator + the "dollhouse" UI (`frontend/src/pages/Safety.jsx`).

**New for the Guardian:**
1. **Presence** — simulated WiFi/phone connectivity → *auto* occupancy (today it's manual placement).
2. **Situation classifier** — turn "who's home" into a named situation + protection mode.
3. **`woman_alone` security posture** — needs a `gender` attribute; the current types are all care-oriented.
4. **Guardian LLM** — reasons over presence + vulnerability + patterns + live sensors + ambient sounds → posture + protective **actions** + spoken line + family escalation.
5. **Two-way check-in** (Whisper) — stand down false alarms; a human touch.

---

## 2 · Presence — simulated WiFi/phone (auto occupancy)

Each `PersonProfile` gains a **`phone_id`** (their handset). A person is **home**
when their phone is "connected to home WiFi." The dashboard shows a **presence
strip**: one toggle per member — 📶 *connected* / ⚪ *away*. Toggling drives the
`people_home` map automatically (no more manual "placement").

- **Backend:** the assess request carries `connected_phones: [phone_id, …]`; the
  server maps phones → persons → `people_home`. (A tiny, honest simulation of a
  router's client list.)
- **Realism note (say this to judges):** "In production this reads the router's
  connected-device list / BLE beacons; here we simulate that so you can drive it."
- Departures/arrivals still also come from `ARRIVE`/`LEAVE` presence events, so
  both paths feed occupancy.

---

## 3 · Situation classifier (deterministic)

New pure function `classify_situation(occupants, profiles, now) -> Situation`.

**Output:** `{ situation, mode, most_vulnerable, alone, is_night, rationale }`.

**Situations:** `empty` · `all_safe` · `elderly_alone` · `child_alone` ·
`woman_alone` · `pregnant_alone` · `unwell_alone` · `multiple_vulnerable` ·
`vulnerable_with_support`.

**Rules (in order):**
1. No occupants → `empty` (mode `calm`; watch for intrusion only).
2. A capable **NORMAL adult** present with any vulnerable person → `vulnerable_with_support` (mode `care-light`).
3. Exactly one occupant, and they are vulnerable/alone:
   - `elderly` → **elderly_alone** · mode **care**
   - `child` → **child_alone** · mode **care+security** (security ↑ at night)
   - `pregnant` → **pregnant_alone** · mode **care**
   - `unwell` → **unwell_alone** · mode **care**
   - `normal` **female** adult → **woman_alone** · mode **security**
   - `normal` male adult → `all_safe` (mode `calm`)
4. Multiple vulnerable, no capable adult → `multiple_vulnerable` (mode = max of their modes).
5. `is_night` (22:00–06:00) upgrades any security posture a level.

**Protection modes:**
- **care** → wellbeing focus: inactivity, falls, missed medicine, needs-help, gentle check-ins.
- **security** → intrusion focus: doors/windows/gate at odd hours, unexpected visitors, glass-break (from the **ambient ear**), secure the home, screen/deter, alert family.
- **care+security** → both (child alone).
- **calm** → normal ambient watch.

---

## 4 · What each mode watches (reuses + adds detectors)

| Mode | Deterministic signals it leans on | Guardian actions it may take |
|------|-----------------------------------|------------------------------|
| **care** | `global_inactivity`, missed medicine/activity, `health_alert`/`sos`, stove/gas duration | check-in, soft lights, notify family, (on SOS/health) emergency |
| **security** | `unsafe_at_night` (door/window open), `unexpected_activity` (off-schedule arrival), **ambient**: glass-break / knock / doorbell, motion while phones away | lock main door, porch/indoor lights on ("occupied" look), screen visitor ("who's there?"), start recording, alert family |
| **calm** | ambient safety only (smoke/glass) | secure on leaving; nothing intrusive |

**New Guardian-specific concerns** (derived, not new detectors — computed in the
Guardian layer from existing signals + situation):
- **`unscreened_visitor`** — a doorbell/knock/arrival while a vulnerable person is
  alone → do NOT auto-open; announce + notify.
- **`intrusion_signal`** — glass-break, or a door/window opening while all phones
  are away (nobody should be home) → alert + record.
- **`night_exposure`** — an entry point open at night while `woman_alone` /
  `child_alone` → secure + heighten.

---

## 5 · The Guardian LLM (`backend/safety/logic/guardian.py`)

Reuses the Bedrock→Groq scaffolding from [`logic/narrator.py`](../backend/safety/logic/narrator.py).

**Input payload:**
```json
{
  "situation": "woman_alone", "mode": "security", "is_night": true,
  "most_vulnerable": {"name": "Priya", "vulnerability": "normal", "gender": "female", "relation": "daughter"},
  "occupants": [{"name":"Priya","vulnerability":"normal","gender":"female"}],
  "time": "23:10",
  "safety": {"status":"needs_attention","score":72,"vulnerable_alone":true},
  "active_devices": ["main_door"], "open_entry_points": ["main_door"],
  "recent_events": [{"device":"main_door","action":"OPEN","t":"23:08"}],
  "ambient_signals": [{"sound":"doorbell","t":"23:09"}],
  "anomalies": [{"type":"unsafe_at_night","detail":"main door open at 23:08"}],
  "learned_context": ["nobody usually arrives after 22:00"]
}
```

**Output (strict JSON):**
```json
{
  "posture": "calm|watchful|heightened|concern|emergency",
  "headline": "Priya is home alone at night; the main door just opened.",
  "spoken": "It's late and you're home alone — I've locked the main door and turned the porch light on. Shall I ask who's there?",
  "watch_items": ["main door", "any unexpected visitor"],
  "protective_actions": [
    {"device":"main_door","action":"LOCK","reason":"secure entry at night","requires_confirmation":false},
    {"device":"porch_light","action":"ON","reason":"deter / visibility","requires_confirmation":false}
  ],
  "checkin": {"should": true, "prompt": "Priya, are you expecting anyone?"},
  "notify_family": {"should": true, "urgency": "concern",
                    "message": "Priya is home alone at 11pm and the door opened unexpectedly. Awaas has secured the home and is checking in."}
}
```

**Guardrails (deterministic, enforced server-side):**
1. `protective_actions[].device` must be a **known device** → else dropped.
2. **Safety floor:** `posture` cannot be below the deterministic status
   (`EMERGENCY` status → posture ≥ `concern`; a live `sos`/`health`/`global_inactivity`
   forces `emergency` + `notify_family.should=true`).
3. In **security** mode, a stand-down cannot come from silence — an active
   intrusion signal keeps the posture regardless of the LLM's phrasing.
4. If the LLM call fails → deterministic fallback posture + templated line
   (feature never blocks).

---

## 6 · Two-way check-in (Whisper) — kills false alarms, feels human
- `POST /guardian/{hid}/checkin/respond` `{audio_base64|text}` → Groq Whisper →
  LLM verdict `{verdict: stand_down|escalate|uncertain, reason, family_message}`.
- **care** concerns (inactivity) may `stand_down` on a reassuring reply
  ("I'm just resting"). **security** intrusion may **not** be stood down by
  silence; `uncertain` always escalates.
- Directly closes the false-alarm class we fixed earlier in the safety engine.

---

## 7 · Protective-action catalog (security mode)
`main_door → LOCK`, `porch_light / indoor lights → ON` ("occupied" look),
`camera → RECORD` (flag only), `intercom → ANNOUNCE "who's there?"`,
`notify_family`, `alarm → ON` (only on confirmed intrusion). Care mode adds
`nursery/room light → soft ON`, `speak reassurance`, `notify_family`,
`emergency_contacts` on SOS/health. Safety-critical actions (alarm, unlock) always
`requires_confirmation` unless a confirmed emergency.

---

## 8 · Family escalation
Every `notify_family.should=true` renders a **family-alert card** with the
generated message + urgency, a "Notify now" button, and the list of what the
Guardian already did ("locked doors 23:08 · porch light on · checking in"). This
is the remote-family reassurance angle.

---

## 9 · Data-model changes
- `PersonProfile` + `gender: "male"|"female"|None`, `phone_id: str|None`.
- New `models/guardian.py`: `Situation`, `ProtectiveAction`, `GuardianAssessment`.
- **Roster** (`Safety.jsx`) add a lone **normal adult female** (e.g. **Priya**,
  daughter) for the `woman_alone` demo; tag genders on existing members
  (grandma/grandpa/meera…). `aarav` (child) covers child-alone.
- New DynamoDB: none required — the Guardian assessment is computed per request
  (like the current evaluate). (Optional `Safety_GuardianLog` table only if we
  want a persistent family feed.)

---

## 10 · Endpoints (safety service :8006)
- `POST /guardian/{hid}/assess` — body: `{connected_phones[], active_devices[], device_on_since{}, ambient_signals[], current_time, profiles?}` → runs presence→occupancy → `classify_situation` → existing `evaluate_context` (overlay/score) → Guardian LLM → returns `{situation, mode, safety, guardian}`.
- `POST /guardian/{hid}/checkin/open` → returns the spoken check-in prompt.
- `POST /guardian/{hid}/checkin/respond` → Whisper + verdict.
- (reuse) `POST /admin/profiles/{hid}?preset=` — add `woman_alone`, `child_alone` presets.

---

## 11 · Frontend — the Guardian panel (on the Safety page)
- **📶 Presence strip** — one connect/away toggle per member (drives occupancy).
- **Situation banner** — big, e.g. *"🧕 Priya is home alone · Night · Security watch"* or *"👵 Saroja is home alone · Care watch"*, with the mode chip + safety score.
- **Guardian card** — posture color, `headline`, the 🔊 `spoken` line, and **watch items**.
- **Protective actions taken** — list with icons; `requires_confirmation` ones get a **Confirm** button (and paint the device on the dollhouse: door locks, porch light glows).
- **📞 Check in** — voice (Whisper) → stand-down / escalate.
- **🧡 Family alert** — generated message + "Notify now" + what-the-guardian-did log.
- The existing dollhouse stays for painting device/sound/signal state that feeds `assess`.

---

## 12 · Demo flows (one per situation)
1. **Elderly alone (care):** Grandma's phone connected, everyone else away →
   banner "Care watch." Trigger inactivity → Guardian: soft check-in → judge
   answers "just resting" → stand down (logged); silence → escalate to family.
2. **Woman alone at night (security):** Priya's phone the only one connected,
   clock 23:10, open the main door (or fire an **ambient doorbell/glass-break**) →
   Guardian locks the door, porch light on, "who's there?", family alert. *This is
   the showpiece — ties presence + ambient ear + patterns + security posture.*
3. **Child alone (care+security):** Aarav connected after school, a
   knock/doorbell → "don't open for strangers," notify parents; a device left on →
   gentle safety nudge.
4. **Pregnant/unwell alone (care):** Meera alone, a needs-help signal / long
   inactivity → quick family escalation with a caring message.

---

## 13 · Build order (after sign-off)
1. `gender`/`phone_id` on profiles + roster (Priya) + presence→occupancy mapping.
2. `classify_situation` (deterministic) + situation banner on the UI.
3. `guardian.py` LLM + `POST /guardian/{hid}/assess` + guardrails; Guardian card + actions.
4. Ambient/security wiring (doorbell/glass-break/night-door as security inputs).
5. Two-way check-in + family alert card.
6. Presets + polish + the 4 demo flows.

## 14 · Risks & guardrails
- **Never suppress a real emergency** (safety floor, §5).
- **No hallucinated actions** (resolve-or-drop devices).
- **Privacy/optics of "surveillance":** frame as *protective, consent-based, in
  the family's own home* — no cloud recording; ambient audio is event-only
  (reuse the ambient-ear privacy stance).
- **LLM latency/limits:** deterministic fallback posture; the situation banner +
  safety score are always deterministic, so the screen is never blank.
- **Rate limits:** assess runs on board changes (debounced), not continuously.

## 15 · Open questions
1. Persist a **family activity log** (needs a small table) or keep it session-only?
2. Add a **camera/vision** stretch (a "person at the gate" frame → describe) or
   stay audio-only for security?
3. Should `woman_alone` apply to *any* lone adult at night (gender-neutral
   "someone alone at night" security) with `woman_alone` as a stronger sub-case —
   arguably less assumption-laden? (Recommended to consider.)
