# Awaas AI — Roadmap & Future Scope

> The guiding principle carries through every phase:
> **deterministic engines establish ground truth → the LLM reasons and speaks →
> the human stays in control → privacy stays on the edge.**
> Each phase adds a new *sense* or a new *kind of reasoning* on top of the same
> explainable core — never a black box bolted on.

---

## Phase overview

| Phase | Theme | Status | Headline capability |
|:---:|---|:---:|---|
| **1** | Foundation — *learn the home* | ✅ Delivered | Deterministic pattern engine + microservices + dashboard |
| **2** | Contextual & Ambient Intelligence — *understand & adapt* | ✅ **Delivered (current build)** | LLM reasoning over patterns, the household "ear", the Guardian |
| **3** | Multimodal Perception & Full Guardian — *see & protect* | 🔜 Next | **Camera vision** (falls, intruders, visitors) + full presence-aware protection |
| **4** | Predictive & Autonomous — *anticipate* | 🔭 Future | Health-decline prediction, edge/on-device models, real IoT + wearables |
| **5** | Platform & Ecosystem — *scale the care* | 🌍 Vision | Caregiver network, emergency-services & telehealth integration, community safety mesh |

---

## Phase 1 · Foundation — *learn the home* ✅
The bedrock everything else stands on.
- **Deterministic pattern engine** — time / sequence / duration extraction with explainable confidence (no ML, fully auditable).
- **7-service microservice platform** (mood, behaviour, patterns, devices, orchestrator, safety, gateway) on DynamoDB.
- **Vulnerability-aware safety overlay** — the same anomalies re-read by *who's home*.
- **LLM narrator** with graceful Bedrock→Groq→template fallback.
- **Mood & cognitive-load engine** (voice + behaviour → ambience).

## Phase 2 · Contextual & Ambient Intelligence — *understand & adapt* ✅ *(this build)*
Where the home stops merely *following rules* and starts *reasoning*.
- **Contextual Pattern Discovery** — an LLM finds *conditional* routines the statistics can't express ("AC only on hot days"), each **re-verified against real history** before it's shown.
- **Voice/Text Context Adaptation** — the family *tells* the home about an occasion ("tomorrow is Diwali", "guests coming"); an LLM proposes **temporary, dated adjustments** on top of the learned patterns, and the **daily routine visibly re-arranges** (reversible, base truth untouched).
- **The Household "Ear"** — real ambient-sound understanding via an audio-native LLM (pressure cooker, baby cry, smoke alarm…) turned into **insight** by per-sound sense-making (rate / burst / surface / instant) and spoken narration.
- **The Guardian (elderly-alone)** — heightened watch when a vulnerable person is alone; the LLM **triages every raised alarm to the single most dangerous one** and **checks in with the person before alarming** for non-emergencies, escalating to family on distress or silence.

> **Why this is the right "middle":** the home can now perceive (sound), reason
> (contextual + occasion adaptation), and protect (Guardian) — all still
> explainable and human-in-the-loop. Phase 3 adds the one sense it's missing —
> **sight** — and widens protection to every vulnerable situation.

---

## Phase 3 · Multimodal Perception & Full Guardian — *see & protect* 🔜

### 3A · Camera Vision (privacy-first)
Give the home **eyes** to complement its ear — fused, not standalone.
- **Fall & collapse detection** — on-device **pose estimation**; a person on the floor + the Guardian's inactivity signal = high-confidence emergency (vision **confirms** what audio/patterns suspect, cutting false alarms).
- **Intruder / stranger detection** — a person at the door/gate classified **known vs unknown** (family face-embeddings kept locally); an unknown person while a vulnerable member is alone → security posture (ties into the Guardian's "woman/child alone" modes).
- **Visitor screening** — "who's at the door?" → describe the visitor (delivery / neighbour / stranger) so the elder never has to open blindly.
- **Activity & wellbeing recognition** — is the elder moving normally, eating, taking medicine? Gentle, aggregate wellbeing signals — not surveillance clips.
- **Gesture / distress recognition** — a raised-hand SOS or a distress posture triggers help without a wearable.
- **Package / delivery & pet detection** — everyday convenience.
- **Vision + Audio fusion** — glass-break *heard* **and** motion *seen* while everyone's away = confirmed intrusion; a cry *heard* **and** a fall *seen* = confirmed emergency. Two senses, far fewer false alarms.

**Privacy by design (non-negotiable):** all inference runs **on-device / on-prem**;
frames are processed to **skeletons/embeddings**, never streamed or stored;
face data stays local; a visible "watching" indicator + per-room opt-in + guest
mode. *We extract meaning, not footage.*

### 3B · The Full Guardian (all vulnerable situations)
Extend the delivered elderly-alone flow (per [`docs/GUARDIAN_SPEC.md`](GUARDIAN_SPEC.md)):
- **Presence-aware occupancy** — real WiFi/BLE device presence auto-detects *who's home* (today simulated).
- **Situation classifier** — `elderly_alone`, `child_alone`, `woman_alone`, `pregnant/unwell_alone` → **care mode** vs **security mode**.
- **Protective actions** — lock doors, "occupied-look" lighting, screen visitors, record on confirmed threat, tiered family escalation.
- **Two-way conversational check-ins** — natural back-and-forth, not one-shot.

---

## Phase 4 · Predictive & Autonomous — *anticipate* 🔭

- **Health-decline prediction** — trend analysis over weeks (routine drift, slower mornings, reduced activity, cough persistence) → a gentle "worth a doctor visit" nudge to family, *before* a crisis. LLM forms the hypothesis; deterministic trends verify it.
- **Real hardware integration** — wearables (HR/SpO₂/fall accelerometer), smart-plugs, door/window/gas sensors, smart locks; a driver layer behind the existing event schema.
- **Edge / on-device models** — quantised LLMs + audio/vision models running locally for zero-latency, offline-capable, privacy-max operation; cloud only as fallback.
- **Federated learning** — homes improve the shared models **without sharing raw data**.
- **Autonomous micro-decisions** — pre-cool before a hot afternoon, pre-heat the geyser on cold mornings, energy-optimise around the learned routine (extends the contextual/adaptation engines).
- **Digital-twin simulation** — a full "what-if" model of the home for testing scenarios and caregiver planning (the dollhouse, grown up).

## Phase 5 · Platform & Ecosystem — *scale the care* 🌍

- **Caregiver & family app** — remote dashboard, the Guardian's daily wellbeing narrative, one-tap check-in, shared alerts across relatives.
- **Emergency-services & telehealth integration** — auto-share location/context with ambulance/police on a confirmed emergency; teleconsult hand-off with the wellbeing history.
- **Alexa Smart-Home skill + regional voice** — deep Alexa integration; multilingual via Whisper + LLM (Hindi, Tamil, Telugu, Bengali… — *Bharat's next billion*).
- **Community safety mesh** — opt-in neighbourhood layer (a confirmed intrusion alerts nearby homes; elders looking out for elders).
- **B2B — elder-care & assisted living** — the Guardian at facility scale; **insurance** partnerships (verified safety → lower premiums).
- **Skill marketplace** — third-party sensors, detectors, and care "skills" on the open event schema.

---

## Cross-cutting themes (every phase)

| Theme | Commitment |
|---|---|
| **Privacy-first** | On-device/edge inference; extract *meaning*, not raw audio/video; local face/voice data; visible indicators + consent + guest mode. |
| **Explainability** | Deterministic ground truth under every LLM decision; every alarm traces to a real signal; the LLM never invents, only reasons (resolve-or-drop, safety floors). |
| **Human-in-the-loop** | Check-in-before-alarm, preview-and-confirm adaptations, reversible overlays — the family is always in control. |
| **Graceful degradation** | Every AI call has a deterministic fallback; the home is never blank or silent when a model is down. |
| **Bharat-first** | Indian household context (joint families, festivals, domestic help, water motors, pooja routines) and Indian languages, from day one. |

---

## How it plugs into *today's* code (credibility, not fantasy)
- **Vision** rides the **same event schema** as the ambient ear — a detected
  event ("person on floor", "unknown visitor") flows into the existing
  anomaly / Guardian / narrator pipeline exactly like a sound does.
- **Real sensors & wearables** are just new **event sources** behind the current
  `EventCreate` model — the pattern engine and detectors need no changes.
- **The Guardian** already triages + checks-in; Phase 3 only adds new *situations*
  and *inputs* to a flow that's live today.
- **Predictive health** extends the **contextual-pattern verifier** (already
  measures behaviour over 30 days) from "is this normal?" to "is this drifting?".

> **One line for the judges:** *"Today it hears, reasons, and protects. Next it
> sees. Then it anticipates. Then it scales the care to every home — and it stays
> explainable and private at every step."*
