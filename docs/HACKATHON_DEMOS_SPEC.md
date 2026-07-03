# Awaas AI — Final Demo Build Spec (3 LLM-Reasoning Demos)

> Status: **spec for review** · Target: hackathon final presentation
> Decisions locked: build **Demo 1 (Pattern Intelligence Layer) first**; ambient
> sensing is **genuinely live** — voice via Whisper STT + **real browser-side
> sound-event classification** (YAMNet primary, Teachable Machine fallback for
> the specific demo sounds), with the manual buttons kept only as a last-resort
> stage fallback; this document is the spec to review before any code is written.

---

## 0 · The framing (say this to judges before any demo)

The current pitch is *"Deterministic engines decide what is true; the LLM only
phrases it."* We are now adding LLM **reasoning**, which seems to contradict
that. It doesn't — we upgrade the sentence to:

> **Deterministic engines establish ground truth — they cannot hallucinate.
> The LLM is a reasoning layer *on top* that interprets, prioritizes, and
> perceives. Every LLM suggestion is checked back against deterministic ground
> truth before it becomes an action.**

Concretely, this is enforced in code by three rules the LLM layer always obeys:

1. **The LLM never mutates stored truth.** It annotates, ranks, groups, and
   suggests — it never edits a pattern's `confidence`, deletes an anomaly, or
   writes to DynamoDB directly.
2. **Every LLM reference must resolve to a real object.** Meta-routines may only
   cite `pattern_id`s that exist; suggested actions may only target devices the
   deterministic state knows about. Anything that doesn't resolve is dropped
   server-side (guards against hallucination).
3. **Deterministic detectors still gate safety.** The LLM can *soften* (mark a
   concern as likely-benign, pending confirmation) or *raise* (prioritize), but
   an SOS / health / global-inactivity emergency from the deterministic engine
   is never suppressed by the LLM.

This turns the apparent contradiction into a maturity story.

---

## 1 · Shared building block — the "context reasoner" module

All three demos are the same shape: *feed a deterministic structure + a task to
an LLM, get structured JSON back, validate it against ground truth, render it.*
So we build **one** reusable helper, mirroring the existing
[`patterns/logic/narrator.py`](../backend/patterns/logic/narrator.py) /
[`safety/logic/narrator.py`](../backend/safety/logic/narrator.py) (Bedrock →
Groq → fallback, `truststore` SSL, timeout, JSON-mode parsing).

**New file:** `backend/<service>/logic/llm_reason.py` (one per service that needs
it — patterns + safety; keep them independent twins, like the narrators).

```python
async def reason(
    system_prompt: str,
    user_payload: dict,          # the deterministic structure, as JSON
    *,
    schema_hint: str,            # human description of the JSON we want back
    timeout: float | None = None,
) -> dict | None:
    """Call the configured LLM (Bedrock→Groq), force JSON output, parse it.
    Returns None on any failure so callers can fall back deterministically."""
```

Reuse verbatim from `narrator.py`: `_verify_ctx()`, `_call_groq`/`_call_bedrock`
scaffolding, provider ordering from `settings.llm_provider`, the
`narrator_timeout_seconds` ceiling, and the JSON-extraction regex. This is a
~1 hour lift because it is a refactor of code that already works.

> **Build note:** it is fine to ship Demo 1 by copying the narrator's Groq call
> inline first, then extract `llm_reason.py` when Demo 2 needs it. Don't
> over-engineer the shared module before the second consumer exists.

---

## 2 · DEMO 1 — Pattern Intelligence Layer  *(build first)*

> ✅ **IMPLEMENTED — revised & stronger design (2026-07-01).** During build the
> team refined Demo 1 from "LLM *labels* the deterministic patterns" to "LLM
> *generates a new class of pattern the statistical engine structurally cannot
> express*: **context-conditional routines**." This is a bigger win and is what
> shipped. What was actually built:
>
> - **New demo home `H004`** ([`backend/patterns/tests/sample_data_h004.py`](../backend/patterns/tests/sample_data_h004.py))
>   with three real correlations baked into 30 days of history + a daily
>   `weather_sensor` temperature reading.
> - **Day-annotation + deterministic verification**
>   ([`backend/patterns/logic/day_features.py`](../backend/patterns/logic/day_features.py)):
>   collapses events into per-day feature rows (weekday, temperature, who's home)
>   and *measures* any proposed condition against real days (occurrence rate with
>   vs without the condition, or timing shift).
> - **LLM generator**
>   ([`backend/patterns/logic/pattern_intelligence.py`](../backend/patterns/logic/pattern_intelligence.py)):
>   Groq proposes conditional rules `{device, action, kind, condition, claim}`;
>   each is re-measured by the verifier and **dropped unless the data backs it**
>   (the ground-truth guardrail). Deterministic brute-force fallback if the LLM
>   is down.
> - **Endpoint** `POST /patterns/{id}/contextual` + models in
>   [`backend/patterns/models/contextual.py`](../backend/patterns/models/contextual.py).
> - **Frontend** ([`ContextualPatterns.jsx`](../frontend/src/components/patterns/ContextualPatterns.jsx))
>   on the Patterns page: a "✨ Generate" button + live-context controls
>   (temperature slider / weekend toggle / who's-home chips) that flip each
>   pattern's **"active now"** flag instantly (evaluated client-side).
>
> **Verified end-to-end:** the LLM proposed 4 rules, **3 survived verification**
> — (1) AC only on hot days, (2) porch light ~1 h later on weekends, (3) bedroom
> AC only when mother commutes home — with the weekday-vs-occupancy ambiguity
> correctly resolved in favour of occupancy. The original "label/prune/group"
> spec below is kept for historical context.

**One line (as built):** the deterministic engine mines *unconditional* routines;
the LLM generates *context-conditional* routines it structurally cannot express
("AC only when it's hot"), and every rule is re-measured against real history
before it's shown.

**Original one-line (superseded):** the deterministic engine mines raw patterns;
one LLM pass gives them human names, prunes contextual noise, and discovers
cross-device "meta-routines" the per-device statistics structurally cannot see.

### 2.1 Backend

**New module:** `backend/patterns/logic/pattern_intelligence.py`

**New route** (append to [`backend/patterns/routes/patterns.py`](../backend/patterns/routes/patterns.py)):

```
POST /patterns/{household_id}/enhance
```

Flow:
1. `patterns = pattern_service.get_patterns(household_id)` (existing).
2. `events = event_service.get_recent_events(household_id, days=7)` — a sample,
   for temporal context (drift, weekday-only detection). Cap to ~200 events.
3. Build the LLM payload (patterns as compact dicts + event sample).
4. `result = await pattern_intelligence.enhance(patterns, events)`.
5. **Validate against ground truth**, then return.

**Request:** none (household in path). Optional body later:
`{ "include_events": true }`.

**LLM output schema** (what `enhance` asks the model for):

```json
{
  "enrichments": [
    {
      "pattern_id": "TIME#pooja_lamp#ON@07:30",
      "label": "Morning pooja lamp",
      "category": "ritual|departure|arrival|cooking|comfort|security|care|other",
      "relevance": "core|situational|noise",
      "reason": "Fires ~daily at a stable time; part of the morning prayer block."
    }
  ],
  "meta_routines": [
    {
      "name": "Morning pooja ritual",
      "member_pattern_ids": ["TIME#pooja_lamp#ON@07:30", "TIME#temple_bell#ON@07:31", "..."],
      "usual_time": "07:30",
      "description": "Lamp, bell, then bhajan speaker within ~2 min each morning."
    }
  ],
  "drift": [
    {
      "pattern_id": "TIME#grandma_activity#ACTIVE@06:40",
      "note": "Morning activity has shifted ~25 min later over the last 7 days.",
      "direction": "later|earlier|less_frequent|more_frequent"
    }
  ]
}
```

**Server-side validation (the guardrail):**
- Drop any `enrichment.pattern_id` / `meta_routines[].member_pattern_ids` /
  `drift[].pattern_id` that is **not** in the real pattern set.
- Drop meta-routines with `< 2` valid members.
- `relevance` is **advisory metadata only** — we never delete the pattern or
  change its `confidence`. The UI greys "noise" out; the data stays.
- If the LLM call fails/returns `None`, return the raw patterns with
  `enhanced: false` so the page still works (graceful degradation).

**Response model** (`EnhancedPatternsResponse`):

```json
{
  "household_id": "H001",
  "enhanced": true,
  "patterns": [ /* original pattern dicts, untouched */ ],
  "enrichments": { "TIME#...": { "label": "...", "category": "...", "relevance": "...", "reason": "..." } },
  "meta_routines": [ /* validated */ ],
  "drift": [ /* validated */ ],
  "llm_powered": true
}
```
(`enrichments` keyed by `pattern_id` for O(1) UI lookup.)

**Prompt sketch** (system): *"You are a home-routine analyst. You are given
statistically-mined routines (each already proven by real event counts) and a
sample of recent events. Do NOT invent routines or change any numbers. Your job:
(1) give each pattern a short human label and category; (2) mark each as core /
situational / noise with a one-line reason; (3) group patterns that co-occur into
named meta-routines, citing only the given pattern_ids; (4) note any timing
drift visible in the event sample. Return ONLY the JSON schema described."*

### 2.2 Frontend

- **`frontend/src/patternsApi.js`** — add:
  ```js
  enhance: (householdId) =>
    request(`/patterns/${householdId}/enhance`, { method: "POST" }),
  ```
- **`frontend/src/pages/Patterns.jsx`** —
  - Add a **"✨ Enhance with AI"** button near the patterns list.
  - On click → `api.enhance(HID)` → merge `enrichments` into the rendered list:
    - show `label` as the primary title (raw `pattern_id` becomes a subtitle);
    - a small **category chip** (ritual / departure / …);
    - `relevance: "noise"` rows render **greyed + struck-through** with the
      `reason` in a tooltip and a "hide"/"keep" toggle;
  - New **"🔗 Discovered routines"** section listing `meta_routines` (name,
    time, member chips).
  - New **drift badges** ("⏱ drifting later") on affected patterns.
- Keep the pre-enhance view fully functional; enhancement is additive.

### 2.3 Demo script (≈45 s)
1. Show the raw learned-patterns list (looks technical).
2. Click **Enhance with AI**.
3. Patterns snap into human names + categories; 2 rows grey out ("weekend-only,
   likely guests — not a routine"); a **"Morning pooja ritual"** meta-routine
   appears grouping 3 patterns; grandma's row shows **"⏱ drifting later"**.
4. Line: *"The statistics found the facts; the LLM found the meaning — and it
   can only ever point at facts the engine already proved."*

### 2.4 Effort / risk
1 backend module + 1 route + 1 api method + Patterns.jsx additions. **Risk: low.**
No new infra, no state, fully additive, graceful fallback.

---

## 3 · DEMO 2 — Guardian: Elderly Care Companion  *(build second — highest impact)*

**One line:** layer LLM reasoning on the safety engine so it goes from *alarm* to
*care* — a two-way voice check-in that dismisses false alarms, tiered
escalation, and a caring family wellness summary.

### 3.1 Backend (safety service, `:8006`)

**A. Wellness summary** — `POST /safety/{household_id}/wellness`
- Input: reads the day's/week's timeline (`event_service.get_recent_events`) +
  current safety assessment.
- LLM returns a caring narrative for remote family + a `tone`
  (`reassuring|watchful|urgent`) + `highlights[]` (bullet facts, each tied to a
  real event/anomaly so it's grounded).
- Guardrail: `highlights` must cite a real event timestamp or anomaly type.

**B. Two-way check-in** — the false-alarm killer, reuses Whisper:
```
POST /safety/{household_id}/checkin/open      → returns spoken prompt ("Saroja, are you okay?")
POST /safety/{household_id}/checkin/respond    → { audio_base64 | text } → LLM verdict
```
- `respond` transcribes audio via the **existing** Whisper path
  ([`services/mood/bedrock_client.py:transcribe_audio`](../backend/services/mood/bedrock_client.py) —
  factor the STT call into a tiny shared helper or call the mood service over
  HTTP), then the LLM classifies the reply →
  `{ "verdict": "stand_down|escalate|uncertain", "reason": "...", "family_message": "..." }`.
- Guardrail: `stand_down` is allowed for inactivity/care concerns **only**; it
  can never clear an SOS/health emergency (rule 3 above). `uncertain` escalates.

**C. Tiered escalation** — extend the narrator/decision so a care concern maps to
a `response_tier`: `gentle_nudge` (speak to the elder) → `notify_family` →
`emergency`. The LLM proposes the tier; the deterministic status caps it (an
`EMERGENCY` status can't be downgraded below `notify_family`).

### 3.2 Frontend (`Safety.jsx` dollhouse — reuse the board we already know)
- When an inactivity/care concern is active, show a **"📞 Check in"** button →
  plays the prompt, opens a mic capture (reuse the mood page's recorder), sends
  to `/checkin/respond`, shows the verdict:
  - `stand_down` → concern collapses to a calm logged note ("Saroja: 'just
    resting' — dismissed 18:04");
  - `escalate` → generated family alert card.
- Add a **"🧡 Daily wellness"** card that calls `/wellness` and shows the
  narrative.

### 3.3 Demo script (≈60 s)
1. On the dollhouse, toggle **"No movement (5h)"** with grandma alone → Emergency.
2. Click **Check in** → Alexa asks *"Saroja, are you okay?"*
3. Judge speaks *"I'm fine, just resting."* → verdict **stand down**, concern
   dismissed with a logged reason. (This is literally the false-alarm class we
   fixed in code today — now closed by conversation.)
4. Re-run, stay silent → **escalate** → generated message to family.
5. Show the **Daily wellness** card summarizing her day warmly.

### 3.4 Effort / risk
Reuses safety engine + Whisper + dollhouse. **New:** check-in loop + wellness
endpoint + mic wiring on Safety page. **Risk: medium** (conversation state, mic
permissions on stage — pre-grant + have a typed-text fallback on `/respond`).

---

## 4 · DEMO 3 — Ambient Context Engine  *(build third — flashiest, partly simulated)*

**One line:** the home *hears* — a real sound plays (a pressure cooker, a smoke
alarm) or a person speaks, the browser classifies it live, and the LLM fuses the
detected event with deterministic state + who's home to reason out an action.
Decision: **genuinely live** — Whisper for speech, a browser-side sound-event
classifier for non-speech; manual buttons remain only as a stage fallback.

> **Key constraint (why not Whisper for everything):** Whisper is speech-to-text
> only — it cannot recognise a cooker whistle or a smoke alarm. Non-speech
> "sound events" need a dedicated **audio-event classifier**, which we run
> **in the browser via TensorFlow.js** (no backend change, low latency). The
> classifier emits the *same* `label` the buttons used to, so §4.1's backend is
> unchanged — we only swap the *source* of the label.

### 4.1 Backend (safety service reuses `/context/{id}/evaluate` + a new reasoner)
`POST /context/{household_id}/ambient`
- Body:
  ```json
  {
    "signal": { "kind": "sound_event|speech", "label": "pressure_cooker_whistle", "audio_base64": null, "text": null },
    "active_devices": ["kitchen_gas_stove"],
    "device_on_since": { "kitchen_gas_stove": "..." },
    "people_home": { "grandma": true },
    "current_time": "13:20"
  }
  ```
- If `kind == "speech"` and `audio_base64` present → Whisper → `text` (live path).
- Build the deterministic context via existing `evaluate_context(...)`, then call
  the ambient reasoner with `(detected signal, context)` →
  ```json
  { "understanding": "3rd cooker whistle + gas on 25 min → cooking likely done",
    "suggested_action": { "device": "kitchen_gas_stove", "action": "OFF", "requires_confirmation": true },
    "spoken": "The cooking sounds done and the stove's been on a while — shall I turn it off?",
    "severity": "medium" }
  ```
- Guardrail: `suggested_action.device` must exist in `active_devices`/known
  devices, else the action is dropped and only `spoken` guidance is returned.
  Safety-critical actions (`gas OFF`, door lock) set `requires_confirmation:true`.

**Target sound events** (produced by the live classifier; buttons mirror the same
set as a fallback): `pressure_cooker_whistle` · `smoke_alarm` · `glass_break` ·
`baby_cry` · `door_knock`. Whichever source produces the `label`, the reasoning
over it is real.

### 4.2 Frontend — the live sound classifier (browser, TensorFlow.js)

Two models, both running client-side; **no backend audio upload**:

- **Primary — YAMNet (pretrained, 521 AudioSet classes)** via `@tensorflow-models`
  / TF.js. Continuously scores 1 s mic windows; we map the AudioSet labels we care
  about (e.g. *Steam / Whistle / Boiling*, *Smoke detector, smoke alarm*,
  *Glass*, *Baby cry, infant cry*, *Alarm*) → our event set. Gives the honest
  "it recognises real-world sounds out of the box" story.
- **Fallback — Teachable Machine audio model** trained on the *exact* clips we'll
  play on stage (cooker whistle, smoke alarm, glass, + a `background` class),
  exported as a TF.js `speech-commands`/browser-FFT model. Used to disambiguate
  or when YAMNet's confidence for a demo sound is low. **This is what makes the
  stage demo reliable** because it's tuned to our specific sounds and room.
- **Decision policy:** take the higher-confidence of {mapped-YAMNet,
  TeachableMachine} above a threshold (e.g. `> 0.6`); debounce so one whistle
  fires once. Below threshold → no event (silence is fine).
- On a confident detection → `POST /context/{id}/ambient` with
  `{ kind: "sound_event", label }`. Speech path: **push-to-talk mic → Whisper →**
  `{ kind: "speech", audio_base64 }` (unchanged from spec).

**Prep required (team):** record 20–30 s per Teachable-Machine class using the
*actual* speaker + room you'll demo in; commit the exported model under
`frontend/public/models/ambient/`. Ship the YAMNet model from CDN or `public/`.

- New **"👂 Ambient" panel** on the Safety page: a **listening toggle** (starts
  the classifier + shows a live "heard: …" readout with confidence), a
  **push-to-talk mic** for speech, and a small **manual event row** (stage
  fallback only). Shows the LLM `understanding` + `spoken` line + an **action
  card** with a **Confirm** button for `requires_confirmation` actions (which
  then paints the device off on the dollhouse).
- Honest caption: *"Live mic → on-device sound classifier (YAMNet) with a model
  tuned to these sounds; speech uses Whisper. Nothing is uploaded for
  classification — it runs in your browser."*

### 4.3 Demo script (≈45 s)
1. Turn on the gas stove, move clock to 13:20 (grandma home alone), hit **Listen**.
2. **Play a real pressure-cooker whistle** from a phone → panel shows *heard:
   pressure cooker whistle (0.9)* → home says *"Cooking sounds done and the
   stove's been on a while — shall I turn it off?"* → **Confirm** → stove paints
   off on the board.
3. Then push-to-talk and say *"I've fallen"* → instant Emergency reasoning.
4. Line: *"Sensors tell it what's on; ambient understanding tells it what's
   happening — it actually hears the room, and still asks before touching the gas."*

### 4.4 Effort / risk
Reuses Whisper + `/evaluate` + dollhouse. **New:** ambient endpoint + panel +
**two browser TF.js models** (YAMNet load/label-mapping; a trained Teachable
Machine model). **Risk: medium-high** — real audio ML on a noisy stage is the
biggest reliability variable in the whole plan. Mitigations: TM model trained in
the venue/on the demo speaker; confidence threshold + debounce; and the manual
event row as an always-available fallback so the demo can never hard-fail.

---

## 5 · Build order, sequencing, and reuse

| # | Demo | Depends on | Net-new backend | Net-new frontend |
|---|------|-----------|-----------------|------------------|
| 1 | Pattern Intelligence Layer | — | `pattern_intelligence.py` + 1 route | Patterns.jsx panel + api method |
| 2 | Guardian (elderly) | shared reasoner, Whisper helper | 3 endpoints (wellness, check-in ×2) + tiering | Safety.jsx check-in + wellness card |
| 3 | Ambient Context | shared reasoner, Whisper helper, `/evaluate` | `/ambient` endpoint | Ambient panel + **YAMNet + Teachable Machine TF.js models (client-side)** |

Extract `logic/llm_reason.py` when starting Demo 2 (its second consumer).
Extract a shared **STT helper** at the same time (Demos 2 + 3 both need Whisper;
today it lives only in the mood service).

## 6 · Cross-cutting risks & mitigations
- **LLM latency/timeout on stage** → keep `narrator_timeout_seconds` ceiling;
  every endpoint returns a deterministic fallback; pre-warm one call before demo.
- **Hallucinated references** → the resolve-or-drop validation (rule 2) on every
  endpoint.
- **Mic permissions on stage** → pre-grant in the browser; typed-text fallback on
  every audio endpoint.
- **Groq rate limits** → the Bedrock→Groq→template chain already handles this;
  keep the key fresh (see prior note).
- **Philosophy pushback from judges** → lead with §0.

## 7 · Open questions for the team
1. Household scope: Demo 1 runs on patterns `H001`; Demos 2–3 on safety `E001`.
   Keep them separate, or unify the demo household?
2. Do we want Demo 1's "noise" toggle to *persist* a hidden flag, or stay
   session-only? (Spec assumes session-only to preserve "LLM never mutates
   truth"; a persisted **human-approved** hide is defensible if we want it.)
3. Presentation order on stage — recommended: **1 → 3 → 2** (technical proof →
   flashy hook → emotional close), even though we *build* 1 → 2 → 3.