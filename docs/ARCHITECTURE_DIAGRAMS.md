# Awaas AI — Architecture Diagrams

Block diagrams and identifier reference for the platform:

0. **Production Architecture (AWS)** — the full cloud topology
1. **Pattern Recognition System** (`backend/patterns/`)
2. **Adaptive Safety Intelligence** (`backend/safety/`)

The two intelligence engines share the same core philosophy: **patterns are
discovered deterministically (no LLM)** — the LLM only *consumes* the finished
`ContextObject`.

---

## 0 · Production Architecture (AWS)

Request flows left → right through six layers: **clients → auth → load balancer
→ compute → AI & data → outputs**. In local development the same services run
behind a FastAPI gateway (see the platform [`README.md`](../README.md)).

```mermaid
flowchart LR
    %% ─── 1 · Clients ───
    subgraph C["1 · CLIENTS"]
        direction TB
        MOB["📱 Mobile App"]
        WEB["🌐 Web App"]
        ALX["🔊 Alexa /<br/>Voice Assistant"]
    end

    %% ─── 2 · Auth + Entry ───
    subgraph A["2 · AUTH + ENTRY"]
        direction TB
        COG["🔐 Amazon Cognito<br/>JWT auth · user pools"]
        APIGW["🚪 API Gateway<br/>JWT validation · rate limiting · routing"]
    end

    %% ─── 3 · Load Balancer ───
    subgraph LB["3 · LOAD BALANCER"]
        ALB["⚖️ Application Load Balancer<br/>path routing · health checks · auto scaling"]
    end

    %% ─── 4 · EC2 Auto Scaling Group ───
    subgraph EC2["4 · EC2 INSTANCES · Auto Scaling Group"]
        direction TB
        I1["🟢 Instance 1 · Mood Analysis<br/>Voice/Text → Whisper STT → LLM mood"]
        I2["🔵 Instance 2 · Behavior Analysis<br/>Scroll · Tap · Idle · Swipe → cognitive load"]
        I3["🟠 Instance 3 · Device Pattern Engine<br/>learns routines · detects anomalies"]
        I4["🔴 Instance 4 · Safety Intelligence<br/>vulnerable monitoring · scoring · alerts"]
        I5["🟣 Instance 5 · Orchestrator<br/>collects signals → LLM reasoning → actions"]
        CACHE[("⚡ DynamoDB Cache<br/>native TTL · per instance")]
    end

    %% ─── 5 · AI & Data ───
    subgraph AID["5 · AI & DATA"]
        direction TB
        BR["🧠 NVIDIA Nemotron 3 Super 120B<br/>primary · via AWS Bedrock"]
        GQ["🧠 Groq LLaMA 3.3 70B<br/>fallback"]
        DDB[("🗄️ Amazon DynamoDB<br/>Events · Patterns · State<br/>Mood History · Safety Profiles")]
        S3[("🪣 Amazon S3<br/>logs · voice files")]
    end

    %% ─── 6 · Outputs ───
    subgraph OUT["6 · OUTPUTS"]
        direction TB
        O1["💡 Adjust Ambience<br/>lights · music · temperature"]
        O2["🔔 Notifications<br/>Alexa voice · mobile push"]
        O3["🏠 Device Control<br/>on / off / schedule"]
        O4["🚨 Emergency Alerts<br/>family / caregivers"]
    end

    %% ─── Flow ───
    MOB --> COG
    WEB --> COG
    ALX --> COG
    COG --> APIGW --> ALB
    ALB --> I1 & I2 & I3 & I4 & I5
    I1 --> CACHE
    I2 --> CACHE
    I3 --> CACHE
    I4 --> CACHE
    I1 -. signals .-> I5
    I2 -. signals .-> I5
    I3 -. signals .-> I5
    I4 -. signals .-> I5
    I5 -->|primary| BR
    I5 -. fallback .-> GQ
    I1 --> DDB
    I2 --> DDB
    I3 --> DDB
    I4 --> DDB
    I5 --> DDB
    I1 --> S3
    I5 --> S3
    I5 --> O1
    I5 --> O2
    I5 --> O3
    I4 --> O4

    %% ─── Styling ───
    classDef client fill:#1c2128,stroke:#6e7681,color:#fff;
    classDef auth fill:#3d2a14,stroke:#ff9900,color:#fff;
    classDef lb fill:#2d1f3d,stroke:#a371f7,color:#fff;
    classDef i1 fill:#16301c,stroke:#3fb950,color:#fff;
    classDef i2 fill:#16263d,stroke:#4a90d9,color:#fff;
    classDef i3 fill:#3d2c14,stroke:#d99e4a,color:#fff;
    classDef i4 fill:#3d1820,stroke:#f85149,color:#fff;
    classDef i5 fill:#2d1f3d,stroke:#a371f7,color:#fff;
    classDef cache fill:#241a33,stroke:#a371f7,color:#fff;
    classDef ai fill:#143030,stroke:#2dd4bf,color:#fff;
    classDef data fill:#16263d,stroke:#4a90d9,color:#fff;
    classDef out fill:#3d2c14,stroke:#e3b341,color:#fff;
    class MOB,WEB,ALX client;
    class COG,APIGW auth;
    class ALB lb;
    class I1 i1;
    class I2 i2;
    class I3 i3;
    class I4 i4;
    class I5 i5;
    class CACHE cache;
    class BR,GQ ai;
    class DDB,S3 data;
    class O1,O2,O3,O4 out;
```

**Legend** — `──▶` synchronous flow · `╌╌▶` external / fallback call · `⚡` DynamoDB cache (native TTL).

### Cross-cutting shared services

These observe and support every layer:

| Service | Role |
|---------|------|
| 📊 **Amazon CloudWatch** | metrics, logs & alarms across all instances |
| 🔑 **AWS Secrets Manager** | API keys (Groq), DB creds, Bedrock access |
| 📣 **Amazon SNS / SES** | emergency alert delivery (SMS / email / push) |
| 🪣 **Amazon S3** | shared logs & archived voice files |

### AWS → local mapping

| AWS layer | Service | Maps to (local) |
|-----------|---------|-----------------|
| Clients | Mobile · Web · Alexa | React dashboard `:5173` |
| Auth + Entry | Cognito + API Gateway | FastAPI gateway `:8000` |
| Load Balancer | Application Load Balancer | gateway path-routing |
| Compute (ASG) | 5 EC2 instances | the 6 FastAPI services (`:8001`–`:8006`) |
| AI & Data | Bedrock → Groq · DynamoDB · S3 | Bedrock/Groq · DynamoDB Local `:8100` |
| Outputs | Ambience · Notifications · Device control · Emergency alerts | device + narration responses |

---

## 1 · Pattern Recognition System

### Block diagram

```mermaid
flowchart TB
    A["📥 <b>EVENTS</b><br/>device · action · time<br/>(fan OFF, door OPEN…)"]
    B["🗄️ <b>EVENT STORE</b><br/>30 days of history"]
    C["🧠 <b>PATTERN ENGINE</b><br/>Time · Sequence · Duration<br/><i>deterministic, no AI</i>"]
    D["📚 <b>LEARNED PATTERNS</b><br/>+ confidence score"]
    E["🏠 <b>CURRENT STATE</b><br/>who's home · what's ON"]
    F["⚖️ <b>COMPARE</b><br/>patterns vs. now<br/>→ detect anomalies"]
    G["📦 <b>CONTEXT OBJECT</b><br/>situation + anomalies"]
    H["🤖 <b>LLM BRAIN</b><br/>decides actions"]

    A --> B --> C --> D
    D --> F
    E --> F
    F --> G --> H

    classDef ev fill:#1e3a5f,stroke:#4a90d9,color:#fff,stroke-width:2px;
    classDef pat fill:#1e4620,stroke:#3fb950,color:#fff,stroke-width:2px;
    classDef ctx fill:#5c3d1e,stroke:#d99e4a,color:#fff,stroke-width:2px;
    classDef out fill:#3d1e5c,stroke:#a371f7,color:#fff,stroke-width:2px;

    class A,B ev;
    class C,D pat;
    class E,F ctx;
    class G,H out;
```

### The flow in one line

**Events → learn Patterns → compare with Current State → produce Context → AI acts**

| Block | What it does |
|-------|-------------|
| 📥 **Events** | Raw device actions stream in |
| 🧠 **Pattern Engine** | Learns routines (time / sequence / duration), keeps only confident ones |
| ⚖️ **Compare** | Checks learned patterns against what's happening right now |
| 📦 **Context** | Bundles the situation + any anomalies for the AI |

### Identifiers & parameters

| Stage | Code | Key parameters |
|-------|------|----------------|
| **Events** | `backend/patterns/logic/event_service.py` | `household_id`, `device_id`, `device_type`, `action`, `triggered_by`, `timestamp` |
| **Patterns** | `backend/patterns/pattern_engine/` | `time_bucket_minutes=30`, `min_pattern_occurrences=3`, `min_confidence=0.6`, `analysis_window_days=30` |
| **Confidence** | `backend/patterns/pattern_engine/confidence.py` | `confidence = support × consistency` |
| **State** | `backend/patterns/models/state.py` | `people_home`, `active_devices`, `device_on_since` |
| **Anomaly** | `backend/patterns/context_builder/anomaly.py` | `departure_grace_minutes=60`, `duration_anomaly_factor=2.0`, `max_continuous_active_minutes=720` |
| **Context** | `backend/patterns/context_builder/builder.py` | `ContextObject` → Orchestrator → LLM |

### Pattern types

| Pattern | Example | Key fields |
|---------|---------|-----------|
| **TimePattern** | "living_room_light turns ON around 19:00" | `device`, `action`, `usual_time`, `window_minutes` |
| **SequencePattern** | "door OPEN → fan OFF → light OFF" (departure) | `steps`, `usual_time` |
| **DurationPattern** | "water_motor runs ~15 min, starting ~09:00" | `usual_duration_minutes`, `stddev_minutes`, `usual_start_time` |

---

## 2 · Adaptive Safety Intelligence

The whole left side is the **same pattern pipeline**. Safety adds **one new idea**:
*who is home and how vulnerable are they*.

### Block diagram

```mermaid
flowchart TB
    A["📥 <b>EVENTS</b><br/>device · action · time<br/>+ wearable ALERT / SOS"]
    B["🗄️ <b>EVENT STORE</b><br/>30 days of history"]
    C["🧠 <b>PATTERN ENGINE</b><br/>Time · Sequence · Duration<br/><i>deterministic, no AI</i>"]
    D["📚 <b>LEARNED PATTERNS</b><br/>+ confidence score"]
    E["🏠 <b>CURRENT STATE</b><br/>who's home · what's ON"]
    F["⚖️ <b>COMPARE</b><br/>patterns vs. now<br/>→ detect anomalies<br/>+ night / inactivity / SOS"]
    G["📦 <b>CONTEXT OBJECT</b><br/>situation + anomalies"]

    P["👥 <b>PEOPLE PROFILES</b><br/>elderly · child · pregnant<br/>unwell · normal"]
    S["🛡️ <b>SAFETY OVERLAY</b><br/>escalate by vulnerability<br/>→ score 0–100 + status"]
    H["🤖 <b>LLM BRAIN</b><br/>alerts &amp; actions"]

    A --> B --> C --> D
    D --> F
    E --> F
    F --> G
    G --> S
    P --> S
    S --> H

    classDef ev fill:#1e3a5f,stroke:#4a90d9,color:#fff,stroke-width:2px;
    classDef pat fill:#1e4620,stroke:#3fb950,color:#fff,stroke-width:2px;
    classDef ctx fill:#5c3d1e,stroke:#d99e4a,color:#fff,stroke-width:2px;
    classDef saf fill:#5c1e2e,stroke:#f85149,color:#fff,stroke-width:2px;
    classDef out fill:#3d1e5c,stroke:#a371f7,color:#fff,stroke-width:2px;

    class A,B ev;
    class C,D pat;
    class E,F ctx;
    class P,S saf;
    class G ctx;
    class H out;
```

### The flow in one line

**Events → Patterns → Compare → Context → Safety Overlay (vulnerability) → AI acts**

| Block | What it does |
|-------|-------------|
| 👥 **People Profiles** | Each member tagged: `elderly`, `child`, `pregnant`, `unwell`, or `normal` |
| 🛡️ **Safety Overlay** | Re-reads every anomaly through a vulnerability lens — *the same open door is "low" for a fit adult but "critical" for an elderly person alone* |
| **Score + Status** | Starts at 100, deducts per anomaly → **Safe / Inactive / Needs-Attention / Emergency** |

### Extra safety detectors feeding the Compare step

| Detector | Fires when |
|----------|-----------|
| 🌙 **Unsafe at night** | Door/window open during 22:00–06:00 |
| 😴 **Global inactivity** | No activity for 4 h (warn) / 8 h (emergency) while vulnerable person home alone |
| ❤️ **Health alert / SOS** | Wearable vital out of range, or panic button pressed → instant Emergency |

### Identifiers & parameters

| Stage | Code | Key identifiers / parameters |
|-------|------|------------------------------|
| **Events** | `backend/safety/logic/event_service.py` | `household_id`, `device_id`, `device_type`, `action` (adds `ALERT`, `SOS`), `triggered_by`, `timestamp`, `metadata` |
| **Patterns** | `backend/safety/pattern_engine/` | `time_bucket_minutes=30`, `min_pattern_occurrences=3`, `min_confidence=0.6`, `analysis_window_days=30` |
| **State** | `backend/safety/models/state.py` | `people_home`, `active_devices`, `device_on_since` |
| **Anomaly** | `backend/safety/context_builder/anomaly.py` | `departure_grace_minutes=60`, `duration_anomaly_factor=2.0`, `max_continuous_active_minutes=720` |
| **Safety detectors** | `backend/safety/context_builder/anomaly.py` | `global_inactivity_warn_minutes=240`, `global_inactivity_emergency_minutes=480`, `night_start_hour=22`, `night_end_hour=6` |
| **Profiles** | `backend/safety/models/safety.py` | `person_id`, `display_name`, `vulnerability`, `emergency_contacts`, `wearable_id`, `relation` |
| **Safety overlay** | `backend/safety/context_builder/safety_overlay.py` | vulnerability weights → escalate severity → `safety_score` (0–100) + `status` |
| **Output** | `backend/safety/models/context.py` | `ContextObject` + `SafetyAssessment` → Orchestrator → LLM |

### Vulnerability weights (the new escalation logic)

| Identifier | Value | Meaning |
|------------|-------|---------|
| `vuln_weight_normal` | `1.0` | Capable adult — no escalation |
| `vuln_weight_child` | `1.7` | Minor at home |
| `vuln_weight_pregnant` | `1.8` | Expecting mother |
| `vuln_weight_unwell` | `1.8` | Recovering / fragile |
| `vuln_weight_elderly` | `2.0` | Senior living independently |
| `supervised_mitigation` | `0.6` | A capable adult present *reduces* risk |

### Anomaly types & base risk rank

| `AnomalyType` | Base rank | Severity scale |
|---------------|-----------|----------------|
| `MISSED_ROUTINE` | 1 | low |
| `DEVICE_LEFT_ON`, `DURATION_EXCEEDED`, `DEVICE_ACTIVE_TOO_LONG`, `MISSED_MEDICINE`, `MISSED_ARRIVAL` | 2 | medium |
| `UNEXPECTED_ACTIVITY`, `INACTIVITY`, `UNSAFE_AT_NIGHT` | 3 | high |
| `GLOBAL_INACTIVITY`, `HEALTH_ALERT`, `SOS` | 4 | critical |

> Escalated rank = `round(base_rank × vulnerability_factor)`, clamped to 0–4 →
> mapped to `["low", "low", "medium", "high", "critical"]`.

### Scoring & status thresholds

| Identifier | Value | Effect |
|------------|-------|--------|
| `_SEVERITY_PENALTY` | low=4, medium=12, high=28, critical=55 | Points deducted from 100 |
| `SafetyStatus.EMERGENCY` | score < 25, or SOS / Health / Global-inactivity | Highest urgency |
| `SafetyStatus.NEEDS_ATTENTION` | score < 60, or any high/critical anomaly | Concern |
| `SafetyStatus.INACTIVE` | only inactivity-type anomalies | Quiet home |
| `SafetyStatus.SAFE` | otherwise | All normal |

### Context types (headline situation)

| `ContextType` | Triggered by |
|---------------|--------------|
| `EMERGENCY` | SOS · Health alert · Global inactivity |
| `SAFETY_ALERT` | Unsafe at night (open door 22:00–06:00) |
| `SECURITY_ALERT` | Unexpected activity (off-schedule entry) |
| `CARE_ALERT` | Inactivity · Missed medicine · Missed arrival |
| `DEPARTURE_ANOMALY` / `DURATION_ANOMALY` | Device left on / running too long |
| `ROUTINE_SUGGESTION` / `NORMAL` | Missed routine / all clear |

---

## Key design principle

Both engines keep pattern discovery **deterministic and explainable**:

```
Events → Pattern Extraction → Household Knowledge → Context Builder → LLM
```

The LLM (Groq / AWS Bedrock) never *discovers* patterns — it only phrases the
already-computed `ContextObject` into natural-language actions and alerts.