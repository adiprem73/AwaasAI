# MoodSense AI — Complete Feature Documentation

## Application Overview

MoodSense AI is a context-aware smart home intelligence platform built for Indian households. It connects to Amazon Alexa and uses a combination of deterministic pattern recognition, LLM-powered natural language generation, and real-time signal analysis to create an adaptive home that responds to its residents' moods, routines, and safety needs.

The platform has three core intelligence pillars:

1. **Mood-Based Environment Adaptation** — detects emotions from speech/behavior and adjusts the home environment in real time
2. **Pattern Recognition & Anomaly Detection** — learns household routines from IoT events and surfaces deviations
3. **Adaptive Safety Intelligence** — protects vulnerable family members (elderly, children, pregnant) through vulnerability-aware monitoring

---

## Architecture

- **Frontend**: React + Vite + TailwindCSS (port 5173)
- **API Gateway**: FastAPI proxy routing to all microservices (port 8000)
- **Microservices**: 6 independent Python (FastAPI) services
- **Database**: Amazon DynamoDB (Local for dev, AWS for production)
- **LLM Providers**: AWS Bedrock (Nvidia Nemotron Super 3 120B) primary, Groq (LLaMA 3.3 70B) fallback
- **Speech-to-Text**: Groq Whisper Large V3 Turbo
- **Infrastructure**: Docker Compose (8 containers + DynamoDB Local)

---

## Feature 1: Mood-Based Environment Adaptation

### What It Does

Detects the emotional state of household members through voice analysis and behavioral signals, then automatically adjusts the smart home environment (lighting, music, notifications) to support their wellbeing — all through a natural Alexa-style interaction.

### Service Architecture

| Service | Port | Role |
|---------|------|------|
| Mood Analysis | 8001 | Speech-to-text + emotion detection |
| Behavior Tracking | 8002 | Interaction pattern analysis |
| Device Control | 8004 | Environment preset computation |
| Orchestrator (Brain) | 8005 | Unifies all signals, calls the Action Engine LLM |

### Pipeline (end-to-end)

```
User speaks to Alexa
        │
        ▼
┌─────────────────────────┐
│  MOOD SERVICE (:8001)   │
│  Audio → Whisper STT    │
│  Text → LLM Mood Analysis │
│  Output: mood, confidence,│
│    cognitive_load, features│
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  BEHAVIOR SERVICE (:8002)│
│  Scroll/tap/idle/swipe  │
│  → Agitation scoring    │
│  → Cognitive load level │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  PATTERN SERVICE (:8003) │
│  Current household state │
│  Active anomalies        │
│  Who is home             │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────────────┐
│  ORCHESTRATOR / ACTION ENGINE   │
│  (:8005)                        │
│  ALL signals → LLM (Bedrock/   │
│  Groq) → Device action decisions│
│  + Alexa spoken response        │
│  + Mood history stored          │
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────┐
│  DEVICE COMMANDS         │
│  Lights: color, brightness│
│  Speaker: genre, volume   │
│  Notifications: mode      │
└──────────────────────────┘
```

### Mood Detection

**Input Methods:**
- Voice audio (base64 encoded) → Groq Whisper transcription → LLM analysis
- Text input (typed or pre-transcribed) → LLM analysis directly
- Audio file upload (mp3/wav/ogg)

**Detected Mood States (9):**
| Mood | Environment Response |
|------|---------------------|
| Calm | Lavender light, 50% brightness, classical music |
| Happy | Bright white light, 75%, upbeat music |
| Stressed | Cool blue, dim 40%, ambient sounds |
| Anxious | Lavender, very dim 35%, nature sounds, DND mode |
| Frustrated | Teal, 45%, lo-fi beats, reduced notifications |
| Sad | Warm gold, 55%, uplifting music |
| Energetic | Green, 80%, electronic music |
| Tired | Deep warm orange, 30%, sleep sounds, DND |
| Neutral | Standard white, 65%, no music |

**Cognitive Load Levels (4):**
| Level | Effect |
|-------|--------|
| Low | Slight brightness/volume boost |
| Moderate | No change |
| High | -10% brightness, -10% volume, reduced notifications |
| Overloaded | -20% brightness, -15% volume, full DND |

### Behavior Analysis Engine

Analyzes interaction signals from Alexa-connected devices (touch screen interactions):

- **Fast/aggressive scrolling** → frustration or searching behavior
- **Rapid tapping** → impatience or agitation
- **Long idle periods** → fatigue or distraction
- **Erratic swipe patterns** → frustration or high cognitive load

Each signal is scored 0-1 for intensity, mapped to an agitation level, then converted to a cognitive load classification. If behavior contradicts speech (e.g., user says "I'm fine" but is tapping aggressively), the system trusts behavior.

### Action Engine (LLM-Powered Decision Maker)

The orchestrator sends ALL context (mood + behavior + patterns + time of day + room) to the Action Engine LLM, which returns:

- `actions`: exact device settings (light hex color, brightness, music genre, volume, notification mode)
- `alexa_response`: what Alexa says to the user (varies by cognitive load — short when stressed, conversational when calm)
- `reasoning`: why these actions were chosen
- `mood_assessment`: LLM's interpretation of the overall situation

**Dual-provider resilience**: Bedrock primary → Groq fallback → hardcoded preset fallback (never fails).

### Real-Time Processing

The orchestrator exposes a WebSocket endpoint (`/live`) for continuous real-time processing:
- Voice text updates trigger immediate mood analysis + action decisions
- Behavior batches are processed and only escalate to the LLM when agitation is high
- Updates push back to the frontend instantly

### Mood History

Every mood change is persisted to DynamoDB (`SmartHome_MoodHistory` table) with:
- Timestamp, mood, cognitive_load, confidence
- Trigger source (voice/behavior/system)
- What Alexa said
- What actions were taken

The frontend displays a grouped timeline with color-coded mood dots, source icons, and confidence percentages.

---

## Feature 2: Pattern Recognition & Anomaly Detection

### What It Does

Learns the household's daily routines by statistically analyzing IoT event history, then compares the current state against those learned patterns in real time to detect deviations — devices left on, routines missed, unusual durations. When anomalies are found, an LLM generates natural Alexa-style notifications.

### Service Architecture

| Component | Location | Role |
|-----------|----------|------|
| Pattern Service | Port 8003 | API + event storage + state management |
| Pattern Engine | `patterns/pattern_engine/` | Statistical extraction from events |
| Context Builder | `patterns/context_builder/` | Anomaly detection (state vs. patterns) |
| LLM Narrator | `patterns/logic/narrator.py` | Natural language generation for alerts |

### Pattern Extraction Pipeline

```
30 days of IoT events in DynamoDB
        │
        ▼
┌───────────────────────────────────────┐
│  TIME-BASED EXTRACTOR                 │
│  Groups by (device, action)           │
│  Clusters time-of-day into 30-min     │
│  buckets, finds dominant bucket       │
│  Computes mean ± stddev              │
│  → "porch_light ON around 19:00"      │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  SEQUENCE EXTRACTOR                   │
│  Sessionizes events (gap < 10 min)    │
│  Hashes signatures per session        │
│  Counts daily repeats                 │
│  → "LEAVE → fan:OFF → light:OFF"     │
│    (departure routine ~08:00)         │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  DURATION EXTRACTOR                   │
│  Pairs ON→OFF per device              │
│  Collects runtime samples             │
│  Mean ± stddev                       │
│  → "water_motor runs ~15 min"         │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│  CONFIDENCE SCORING                   │
│  support = occurrences / window_days  │
│  consistency = 1 - stddev/(2×tol)     │
│  final = support × consistency        │
│  Threshold: min_confidence = 0.6      │
└───────────────────────────────────────┘
```

### Anomaly Detection (5 Detectors)

| Detector | What It Catches | Logic |
|----------|-----------------|-------|
| Device Left On | Fan still ON past its learned OFF time | Compares active_devices vs TimePattern/SequencePattern OFF times + grace period |
| Duration Exceeded | Water motor running 45 min vs usual 15 | Current runtime > usual_duration × anomaly_factor (2.0×) |
| Device Active Too Long | Door open 12+ hours (no duration pattern) | Absolute safety-net: device_on_since > max_continuous_active_minutes (720 min) |
| Missed Routine | Porch light didn't turn on at 19:00 | High-confidence ON pattern's window passed, device not active, no matching event today |
| Unexpected Activity | Helper arrived at 02:30 instead of 09:00 | ARRIVE/ACTIVE event happened but time-of-day is far outside learned window |

### Context Builder Pipeline

```
Current State (who's home, active devices, device_on_since)
    +
Learned Patterns (from DynamoDB)
    +
Recent Events (last 24h)
    +
Current Time
        │
        ▼
┌─────────────────────────────┐
│  RUN ALL 5 DETECTORS        │
│  → List of Anomaly objects  │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  CLASSIFY CONTEXT TYPE      │
│  Priority: SECURITY > CARE  │
│  > DEPARTURE > DURATION >   │
│  SUGGESTION > NORMAL        │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  SELECT RELEVANT PATTERNS   │
│  (linked to anomalies, or   │
│  top-5 by confidence)       │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│  EMIT ContextObject         │
│  (structured JSON for LLM)  │
└─────────────────────────────┘
```

### LLM Narrator

When anomalies are detected, the narrator generates a natural "Alexa says…" response:

**Input**: The full ContextObject (anomalies, patterns, energy facts, time)
**Output**: JSON with `alexa_response` (1-2 spoken sentences with concrete numbers) + `explanation` (3-5 sentence reasoning paragraph)

Example output:
> "The fan in the son's room has been on since 7:30 AM — that's over 3 hours past when it's usually switched off, and turning it off now would save about 0.2 kilowatt-hours. Want me to do that?"

**Energy & Timing Facts**: The narrator is fed pre-computed, grounded numbers (how long a device has been on, how far past its usual time, estimated energy waste). The LLM can only quote these — it cannot hallucinate figures.

**Dual-provider**: Bedrock (Nemotron) primary → Groq (LLaMA 3.3 70B) fallback → deterministic template sentence (never blocks the UI).

### Frontend (Interactive Demo)

The Patterns page provides:
- **Floor plan visualization** with device states (ON/OFF/anomaly pulsing)
- **Simulated clock** — set any time to see what anomalies fire
- **Draft scenario painting** — toggle devices ON/OFF and hit "Go" to evaluate
- **Alexa notification popup** — LLM-generated spoken response
- **Side panel** — context details, patterns, events timeline

### Configuration Knobs

| Setting | Default | Purpose |
|---------|---------|---------|
| analysis_window_days | 30 | How many days of history to analyze |
| time_bucket_minutes | 30 | Clustering granularity |
| min_pattern_occurrences | 3 | Minimum repeats to learn a pattern |
| min_confidence | 0.6 | Threshold to accept a pattern |
| departure_grace_minutes | 60 | How long past schedule before flagging |
| duration_anomaly_factor | 2.0 | How many × usual duration triggers alert |
| max_continuous_active_minutes | 720 | Absolute 12h safety-net |
| missed_routine_min_confidence | 0.7 | Only flag confident missed routines |
| missed_routine_horizon_minutes | 180 | Only flag within 3h of the window passing |

---

## Feature 3: Adaptive Safety Intelligence

### What It Does

Protects vulnerable household members — elderly living alone, children, pregnant or unwell family members — by layering a **vulnerability-aware safety overlay** on top of the pattern recognition engine. The same anomaly (e.g., "door left open") is automatically escalated from "low" to "critical" when a vulnerable person is home alone. The system produces a real-time safety score, detects emergencies (SOS, health alerts, prolonged global inactivity), and generates contextual Alexa alerts.

### Service Architecture

| Component | Port/Location | Role |
|-----------|---------------|------|
| Safety Service | Port 8006 | Independent twin of patterns service, with vulnerability overlay |
| Safety Overlay | `safety/context_builder/safety_overlay.py` | Vulnerability scoring + severity escalation |
| Profile Service | `safety/logic/profile_service.py` | Person profiles (who lives here, their vulnerability level) |
| Anomaly Detectors | `safety/context_builder/anomaly.py` | All 5 pattern detectors + 4 safety-specific ones |

### Person Profiles & Vulnerability Levels

Each household member has a profile with a vulnerability classification:

| Vulnerability | Weight | Example |
|---------------|--------|---------|
| Normal | ×1.0 | Fit adult son/daughter |
| Child | ×1.7 | School-age children |
| Pregnant | ×1.8 | Expecting family member |
| Unwell | ×1.8 | Temporarily ill person |
| Elderly | ×2.0 | Grandparents (primary use case) |

**Supervised Mitigation**: If a capable adult (NORMAL) is also home, vulnerability escalation is reduced by a factor of 0.6× — because someone can respond to problems.

**Vulnerable Alone Detection**: When a non-NORMAL person is home with NO capable adult, `vulnerable_alone = true` and every concern is fully escalated.

### Safety-Specific Anomaly Types

Beyond the 5 pattern-based detectors, the safety engine adds:

| Anomaly Type | What It Means | Example |
|---|---|---|
| INACTIVITY | Elderly person's usual activity ping absent | Grandpa usually active by 06:30, still nothing at 09:00 |
| MISSED_ARRIVAL | Expected person hasn't returned | Child usually home from school by 16:00, absent at 17:30 |
| MISSED_MEDICINE | Medicine routine not confirmed | Smart pill box not opened at 09:00 as usual |
| UNEXPECTED_ACTIVITY | Person/entry at an unusual time | Domestic helper detected at 02:30 instead of 09:00 |
| UNSAFE_AT_NIGHT | Door/window open during night | Main door still open at 23:00 (night window: 22:00-06:00) |
| GLOBAL_INACTIVITY | No activity of ANY kind for hours | The entire home has been silent for 6+ hours during daytime |
| HEALTH_ALERT | Wearable sensor threshold breach | Heart rate below 50 BPM from smartwatch |
| SOS | Explicit panic/fall/help button | Grandpa pressed SOS on wearable at 03:00 |

### Vulnerability Escalation Logic

```
For each detected anomaly:
  1. Look up base_rank (0-4) from anomaly type
  2. Multiply by home vulnerability factor
  3. Round and clamp to [0, 4]
  4. Map to severity label: low / medium / high / critical

Example:
  "Door open at night" → base_rank = 3 (high)
  Elderly alone → factor = 2.0
  Escalated rank = min(4, round(3 × 2.0)) = 4 → "critical"
  (vs. "high" with a normal adult home)
```

### Safety Score (0-100)

Starts at 100, deducts per escalated anomaly:

| Severity | Penalty |
|----------|---------|
| Low | -4 points |
| Medium | -12 points |
| High | -28 points |
| Critical | -55 points |

### Safety Status Classification

| Status | Condition |
|--------|-----------|
| Safe | Score ≥ 60, no high/critical anomalies |
| Inactive | Only inactivity-type anomalies |
| Needs Attention | Score < 60 OR any high/critical anomaly |
| Emergency | SOS / health alert / global inactivity / score < 25 |

### Demo Scenario System

The safety page supports simulating multiple threat scenarios:

| Scenario Key | What It Simulates |
|---|---|
| normal | Safe day, all routines followed |
| inactivity | Grandpa missed his morning activity |
| gas | Kitchen gas stove left running >45 min |
| window_night | Bedroom window still open at 23:00 |
| health | Wearable reports abnormal heart rate |
| sos | Fall detected, SOS triggered |

Multiple threats can be combined (e.g., "gas,window_night") to show compounding risk.

### Who's Home Presets

| Preset | Members | Effect |
|--------|---------|--------|
| elderly | Grandpa + Grandma (both elderly) | Maximum vulnerability (×2.0), always vulnerable_alone |
| child_alone | 8-year-old child | ×1.7, vulnerable_alone |
| pregnant_alone | Expecting mother | ×1.8, vulnerable_alone |
| unwell_alone | Temporarily ill person | ×1.8, vulnerable_alone |
| mixed_support | Elderly + adult son | ×2.0 × 0.6 mitigation = ×1.2 (supervised) |

### Frontend Dashboard

The Adaptive Safety Intelligence page shows:

- **Safety Score Gauge** — circular 0-100 meter with color (green → yellow → red)
- **Home Status** — Safe / Inactive / Needs Attention / Emergency with rationale
- **Floor Plan** — rooms color-coded by worst anomaly severity
- **Vulnerability Monitoring** — each anomaly with severity badge, escalation note (e.g., "escalated from high → critical (×2.0)")
- **Person Cards** — each resident with vulnerability badge, last activity time
- **Activity Timeline** — most recent events with device/room/trigger
- **Who's Home controls** — switch between vulnerability presets live
- **Threat Simulator** — toggle multiple safety scenarios simultaneously

### Alexa Narration (Safety Context)

For the safety page, each detected concern gets its own spoken Alexa line (narrated individually, most severe first). The narrator sees the full vulnerability context and adapts tone:

- Emergency: urgent, direct ("Grandpa's SOS went off — calling your son now.")
- Needs Attention: concerned, informative ("The kitchen gas stove has been running 45 minutes, three times longer than usual — shall I switch it off?")
- Safe: warm, brief ("Everything looks good at home. Grandpa and Grandma both followed their usual routine today.")

---

## Cross-Feature Integration

The three features share infrastructure but operate independently:

| Integration Point | How |
|---|---|
| Pattern Service feeds Orchestrator | Mood decisions consider household anomalies (e.g., stressed mood + devices left on → "Looks like you rushed out — want me to handle the fan?") |
| Shared DynamoDB | Events, state, and patterns tables are common infrastructure |
| Shared LLM providers | Bedrock/Groq with automatic failover across all features |
| Shared Gateway | Single entry point (:8000) routes to all services |
| Independent deployment | Each feature can run alone — Pattern on :8003, Safety on :8006, Mood via :8005 orchestrator |

---

## Technology Summary

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React 19 + Vite 8 + TailwindCSS 4 | Interactive dashboards |
| Backend | Python 3.13 + FastAPI | Async microservices |
| Database | Amazon DynamoDB (Local + AWS) | Event storage, state, patterns, profiles |
| LLM (Primary) | AWS Bedrock — Nvidia Nemotron Super 3 120B | Mood analysis, action decisions, narration |
| LLM (Fallback) | Groq — LLaMA 3.3 70B Versatile | Automatic failover when Bedrock throttles |
| STT | Groq Whisper Large V3 Turbo | Audio transcription |
| Infrastructure | Docker Compose (9 containers) | Local development + demo deployment |
| API Gateway | FastAPI reverse proxy | Unified routing + CORS |

---

## Key Design Principles

1. **Graceful degradation** — Every LLM call has a deterministic fallback; the system never blocks or crashes
2. **Explainability** — Every pattern has a confidence score, every anomaly has a detail string, every action has a reasoning field
3. **No ML in detection** — Pattern learning and anomaly detection are statistical (mean/stddev), deterministic, and auditable
4. **LLM only for language** — AI generates natural phrasing, never decides what is true (that's the deterministic engine's job)
5. **Indian household focus** — Examples, routines, and scenarios reflect joint-family living (elderly parents, children's school schedules, domestic help, water motors, gas stoves)
6. **Privacy-first** — All processing happens on your infrastructure (Bedrock stays in your AWS account, Groq is optional)
