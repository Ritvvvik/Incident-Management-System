# Incident Management System — Design Document

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Tech Stack Choices](#2-tech-stack-choices)
3. [Service Breakdown](#3-service-breakdown)
4. [Design Patterns](#4-design-patterns)
5. [Backpressure Strategy](#5-backpressure-strategy)
6. [Deduplication (Debouncing)](#6-deduplication-debouncing)
7. [MTTR Calculation](#7-mttr-calculation)
8. [Database Schema](#8-database-schema)
9. [Resilience Measures](#9-resilience-measures)
10. [Observability](#10-observability)
11. [Frontend Design](#11-frontend-design)
12. [Attribution](#12-attribution)

---

## 1. Architecture Overview

The system is split into two fault-isolated services following production SRE best practices. If the Incident Service crashes, the Monitoring Service continues collecting and buffering signals — no data is lost. The two services communicate exclusively via Redis Streams, never via direct HTTP calls or shared database writes.

```
Signal Sources (APIs · MCP Hosts · Cache · Queues · RDBMS · NoSQL)
                            │
                  POST /signals (HTTP)
                            │
              ┌─────────────▼────────────┐
              │    Monitoring Service    │  :8000  [authored by student]
              │  ─────────────────────   │
              │  Ingestion gateway       │  ← validates signals, rate limiter
              │  Redis Streams buffer    │  ← backpressure, 10k/sec
              │  Debounce worker         │  ← Redis SETNX dedup
              │  Alert Strategy engine   │  ← Strategy pattern P0/P1/P2
              │  Event publisher         │  ← publishes WorkItemCreated
              │  Metrics printer         │  ← signals/sec every 5s
              └────────────┬─────────────┘
                           │
                    Redis Streams
                  (fault boundary)
                           │
              ┌────────────▼─────────────┐
              │    Incident Service      │  :8001
              │  ─────────────────────   │
              │  Event consumer          │  ← reads WorkItemCreated
              │  State machine           │  ← State pattern [student]
              │  RCA validator           │  ← blocks CLOSED if RCA missing [student]
              │  MTTR calculator         │  ← end_time - start_time
              │  REST API                │  ← serves React dashboard
              └──────────────────────────┘
                           │
         ┌─────────────────┼──────────────────┐
         ▼                 ▼                  ▼
     MongoDB           PostgreSQL         Redis Cache
    (raw signals)     (Work Items·RCA)   (dashboard)
                           │
                      TimescaleDB
                     (signal metrics)
                           │
              ┌────────────▼─────────────┐
              │     React Dashboard      │  :3000
              │  Live Feed               │  ← P0/P1/P2 sorted, auto-refresh 5s
              │  Incident Detail         │  ← raw signals + state controls
              │  RCA Form                │  ← submit RCA, preview MTTR
              └──────────────────────────┘
```

### Why Two Services?

Separating signal ingestion from incident management provides critical fault isolation. The boundary is deliberate:

- **High write pressure** on the Monitoring Service would not affect the Incident Service's ability to serve the dashboard
- **Independent scaling** — the Monitoring Service can be scaled horizontally without touching incident state
- **Independent failure** — a crash in one service does not corrupt or block the other
- **Redis Streams as the fault boundary** — events queue safely between services, replayed on restart

---

## 2. Tech Stack Choices

| Layer | Technology | Reason |
|---|---|---|
| Backend language | Python 3.11 + FastAPI | Async-native, fast to develop, great ecosystem |
| Signal ingestion | HTTP/JSON (REST) | Simple, widely supported, easy to mock in tests |
| In-memory buffer | Redis Streams | Persistent, consumer groups, built-in backpressure |
| Raw signal store | MongoDB | Schema-less, ideal for high-volume heterogeneous payloads |
| Work Items + RCA | PostgreSQL | ACID transactions, enforces state transition integrity |
| Dashboard cache | Redis (key-value) | Sub-millisecond reads, avoids DB hits on every UI refresh |
| Timeseries | TimescaleDB (Postgres extension) | Native time-bucketing, reuses Postgres driver |
| Frontend | React + Vite | Component model fits three-view dashboard cleanly |
| Containerisation | Docker Compose | Single command setup as required by assignment |
| Rate limiting | `slowapi` (FastAPI middleware) | Token bucket, minimal config |
| Async concurrency | `asyncio` + `aioredis` + `asyncpg` | No blocking I/O anywhere in the hot path |

### Why Redis Streams over a message queue (e.g. Kafka)?

Redis Streams was chosen because it provides the same consumer group semantics as Kafka — at-least-once delivery, replay from offset, bounded log — without requiring a separate broker cluster. For a two-service system at this scale, Redis already in the stack was sufficient. Kafka would be the natural upgrade path at production load.

### Why MongoDB for raw signals?

Signals have heterogeneous `payload` fields — a CACHE signal carries `latency_ms`, an API signal carries `status_code`. A rigid relational schema would require an `JSONB` column anyway. MongoDB's document model reflects the data's natural structure and makes signal replay straightforward.

---

## 3. Service Breakdown

### 3.1 Monitoring Service

**Fully authored by student.**

**Responsibilities:** ingest signals, deduplicate, classify severity, write to storage, publish events.

| File | Description |
|---|---|
| `main.py` | FastAPI app, `POST /signals`, `GET /health`, background metrics task |
| `gateway.py` | Validates component type, pushes to Redis Streams, returns `202` immediately |
| `rate_limiter.py` | Token bucket limiter — 1000 req/min per IP via `slowapi` |
| `buffer.py` | Writes raw signals to Redis Streams (`XADD`), never blocks on DB |
| `debounce.py` | Async consumer, Redis SETNX dedup, writes Work Items to Postgres + raw signals to MongoDB with exponential backoff retry |
| `publisher.py` | Publishes `WorkItemCreated` event to `incidents:events` Redis stream |
| `metrics.py` | Background task — prints signals/sec to stdout every 5 seconds |
| `strategies.py` | Full Strategy pattern implementation (ABC, all strategy classes, STRATEGY_MAP, get_alert) |

**Endpoints:**

- `POST /signals` — accepts signal payload, rate limited, returns `202 Accepted` immediately
- `GET /health` — liveness check, returns uptime

---

### 3.2 Incident Service

**Responsibilities:** manage Work Item lifecycle, validate RCA, calculate MTTR, serve REST API.

| File | Description |
|---|---|
| `main.py` | FastAPI app, all REST endpoints, Redis cache invalidation |
| `consumer.py` | Reads `WorkItemCreated` events from Redis Streams |
| `state_machine.py` | State pattern — authored by student |
| `rca.py` | RCA validation + MTTR calculation — authored by student |

**Endpoints:**

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/incidents` | List incidents sorted by severity (Redis cached, 10s TTL) |
| `GET` | `/incidents/{id}` | Detail + raw signals from MongoDB |
| `PATCH` | `/incidents/{id}/state` | State transition via State Machine |
| `POST` | `/incidents/{id}/rca` | Submit RCA, calculate MTTR |
| `GET` | `/health` | Liveness check |

---

## 4. Design Patterns

### 4.1 Strategy Pattern — Alerting

**Authored by student.** Located in `Monitoring_system/strategies.py`.

Different component types require different alert priorities. Instead of growing `if/elif` chains, each component type maps to its own `AlertStrategy` class. Adding a new component type requires adding one class and zero changes to existing code.

```python
class AlertStrategy(ABC):
    @abstractmethod
    def get_priority(self) -> str:
        pass

    @abstractmethod
    def get_description(self) -> str:
        pass

class RDBMSStrategy(AlertStrategy):
    def get_priority(self) -> str:    return "P0"
    def get_description(self) -> str: return "RDBMS Failure"

class CacheStrategy(AlertStrategy):
    def get_priority(self) -> str:    return "P2"
    def get_description(self) -> str: return "Cache Failure"

STRATEGY_MAP = {
    "API":   APIStrategy(),
    "RDBMS": RDBMSStrategy(),
    "QUEUE": QueueStrategy(),
    "CACHE": CacheStrategy(),
}

def get_alert(component_type: str):
    if component_type not in STRATEGY_MAP:
        raise ValueError(f"Unknown component type: {component_type}")
    strategy = STRATEGY_MAP[component_type]
    return strategy.get_priority(), strategy.get_description()
```

**OOP concepts demonstrated:**

- **Abstraction** — `AlertStrategy` defines the contract, hides implementation details
- **Inheritance** — each concrete strategy inherits from `AlertStrategy`
- **Polymorphism** — same `get_priority()` call, different behaviour per subclass
- **Encapsulation** — each class owns its own priority and description logic

**Severity mapping:**

| Component Type | Priority | Rationale |
|---|---|---|
| RDBMS | P0 | Database failures cause cascading data loss |
| API | P1 | Service degradation, user-facing impact |
| MCP_HOST | P1 | Integration failures affect downstream orchestration |
| QUEUE | P1 | Message loss can affect data integrity |
| CACHE | P2 | Latency increase, DB absorbs load |
| NOSQL | P2 | Often read-replica; writes still hit primary |

---

### 4.2 State Machine Pattern — Work Item Lifecycle

**Authored by student.** Located in `Incident_system/state_machine.py`.

Valid transitions are declared in an explicit map. Any attempt to skip a state or go backwards raises an error. `CLOSED` is blocked if RCA is missing or incomplete.

```python
VALID_TRANSITIONS = {
    "OPEN":          {"INVESTIGATING"},
    "INVESTIGATING": {"RESOLVED"},
    "RESOLVED":      {"CLOSED"},
    "CLOSED":        set()
}

def transition(current_state: str, new_state: str, has_rca: bool) -> str:
    if new_state not in VALID_TRANSITIONS[current_state]:
        raise InvalidTransitionError(
            f"Cannot move from {current_state} to {new_state}"
        )
    if new_state == "CLOSED" and not has_rca:
        raise RCARequiredError("RCA must be submitted before closing")
    return new_state
```

**Why an explicit transition map over a chain of if statements?**

The map makes all valid transitions visible at a glance. Adding a new state requires one map entry; nothing else changes. Invalid transitions raise typed exceptions that the REST layer converts to `422 Unprocessable Entity` responses.

---

### 4.3 Ingestion Pipeline — Designed and Built by Student

The full signal ingestion pipeline from gateway to storage was independently designed and implemented by the student.

```
POST /signals
      │
      ▼
 gateway.py          ← validates component type, rejects unknown types
      │
      ▼
 rate_limiter.py     ← token bucket, 1000 req/min per IP
      │
      ▼
 buffer.py           ← XADD to Redis Streams, returns 202 immediately
      │
      ▼ (async, separate worker)
 debounce.py         ← XREAD from Redis Streams via consumer group
      │                  Redis SETNX lock to prevent duplicate Work Items
      │                  exponential backoff retry on DB failure
      │
      ├──► MongoDB    (raw signals — audit log)
      ├──► PostgreSQL (Work Items — source of truth)
      │
      ▼
 publisher.py        ← publishes WorkItemCreated to incidents:events stream
      │
      ▼
 metrics.py          ← background task, prints throughput every 5s
```

**Key decisions made by student:**

1. **`202 Accepted` instead of `200 OK`** — the gateway must not wait for DB confirmation. Returns immediately after the Redis write.
2. **Separate debounce worker** — must run independently so a slow DB never blocks signal ingestion.
3. **Redis `SETNX` for race conditions** — two concurrent workers could both create a Work Item for the same component; atomic `SETNX` prevents this.
4. **Exponential backoff** — flat retries waste resources; 1s → 2s → 4s increasing delay avoids thundering herd on DB recovery.
5. **Consumer groups** — `XREADGROUP` gives each message to exactly one worker, preventing double-processing of the same signal.

---

## 5. Backpressure Strategy

The system handles bursts of 10,000 signals/sec without crashing even when the persistence layer is slow.

**Approach: decouple ingestion from persistence via Redis Streams.**

```
Ingestion Gateway        Redis Streams          DB Worker
─────────────────       ──────────────         ─────────
POST /signals ────────► XADD signals:raw ◄──── XREAD (consumer group)
returns 202 immediately                         writes to MongoDB async
                                                retries with backoff
```

- Gateway never blocks on a DB write — writes to Redis Streams and returns instantly
- If MongoDB is slow, signals queue in Redis Streams (bounded by `MAXLEN 100,000`)
- DB worker uses exponential backoff retry (1s → 2s → 4s) before dead-lettering
- Redis Streams persist to disk — signals survive a Redis restart
- If the Incident Service is down, `WorkItemCreated` events queue in `incidents:events` stream and are replayed on restart

---

## 6. Deduplication (Debouncing)

**Problem:** 100 signals for `CACHE_CLUSTER_01` in 10 seconds → exactly 1 Work Item.

**Race condition fix — Redis SETNX atomic lock:**

```python
created = await redis.set(
    f"lock:workitem:{component_id}",
    "1",
    nx=True,   # Set only if Not eXists — atomic at Redis level
    ex=10      # 10 second TTL — allows new Work Item after incident resolves
)

if created:
    work_item_id = await create_work_item(component_id, signal)
else:
    work_item_id = await redis.get(f"workitem:id:{component_id}")
    await link_signal_to_work_item(work_item_id, signal)
```

`nx=True` ensures only one worker wins the lock even under concurrent load. All subsequent signals for the same component during the TTL window are linked to the existing Work Item rather than creating a new one.

---

## 7. MTTR Calculation

```
MTTR = incident_end (RCA submission time) − incident_start (first signal time)
```

Stored in seconds on the Work Item in PostgreSQL. Calculated when RCA is submitted, stored before the state transitions to `CLOSED`.

```python
def calculate_mttr(incident_start: datetime, incident_end: datetime) -> int:
    delta = incident_end - incident_start
    return int(delta.total_seconds())

def mttr_summary(mttr_seconds: int) -> str:
    hours, remainder = divmod(mttr_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"
```

---

## 8. Database Schema

### PostgreSQL — Work Items (source of truth, transactional)

```sql
CREATE TABLE work_items (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    component_id     TEXT NOT NULL,
    component_type   TEXT NOT NULL,
    priority         TEXT NOT NULL,         -- P0, P1, P2
    state            TEXT NOT NULL DEFAULT 'OPEN',
    start_time       TIMESTAMPTZ NOT NULL,
    end_time         TIMESTAMPTZ,
    mttr_seconds     INTEGER,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE rca (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    work_item_id          UUID REFERENCES work_items(id),
    root_cause_category   TEXT NOT NULL,
    problem_description   TEXT NOT NULL,
    fix_applied           TEXT NOT NULL,
    prevention_steps      TEXT NOT NULL,
    submitted_at          TIMESTAMPTZ DEFAULT NOW()
);
```

### MongoDB — Raw Signals (audit log, schema-less)

```json
{
  "signal_id":    "uuid",
  "component_id": "CACHE_CLUSTER_01",
  "work_item_id": "uuid",
  "error_type":   "CONNECTION_TIMEOUT",
  "payload":      { "latency_ms": 5000 },
  "timestamp":    "2025-05-01T10:00:00Z"
}
```

### Redis — Dashboard Cache

Work item list is cached at key `dashboard:incidents` with a 10-second TTL. Invalidated on every state transition and RCA submission.

---

## 9. Resilience Measures

| Concern | Solution |
|---|---|
| DB write failure | Exponential backoff retry (1s / 2s / 4s) in async worker |
| Duplicate Work Items | Redis `SETNX` atomic lock per `component_id` |
| Gateway overload | Token bucket rate limiter via `slowapi` (1000 req/min per IP) |
| Incident Service crash | Redis Streams queues `WorkItemCreated` events; replayed on restart |
| Invalid state skip | State Machine rejects invalid transitions with typed error |
| RCA bypass | Explicit check blocks `CLOSED` if RCA missing or incomplete |
| Data loss on Redis restart | Streams persist to disk; `MAXLEN 100,000` provides a bounded buffer |
| Cascading failures | Services never share a DB connection pool; failures are isolated |

---

## 10. Observability

Both services expose `GET /health`:

```json
{ "status": "ok", "service": "monitoring", "uptime_seconds": 142.5 }
```

The Monitoring Service prints throughput every 5 seconds:

```
[METRICS] signals_received=10234  signals/sec=847  work_items_created=12
```

**Future improvements:**

- Export metrics to Prometheus (`/metrics` endpoint via `prometheus_fastapi_instrumentator`)
- Add OpenTelemetry trace IDs to correlate signals → Work Items across services
- Structured JSON logging (replace `print` with `structlog`)
- Dead-letter queue for signals that fail all retries

---

## 11. Frontend Design

The React dashboard (`Frontend/`) has three views:

### Live Feed — `LiveFeed.jsx`

- Polls `GET /incidents` every 5 seconds
- Incidents sorted by priority: P0 → P1 → P2
- Color-coded rows: red (P0), amber (P1), blue (P2)
- Clicking a row navigates to Incident Detail

### Incident Detail — `IncidentDetail.jsx`

- Shows Work Item metadata: component, priority, current state, timestamps
- Lists all raw signals from MongoDB associated with this incident
- State transition button — calls `PATCH /incidents/{id}/state` with the next valid state
- Link to RCA Form once state reaches `RESOLVED`

### RCA Form — `RCAForm.jsx`

- Fields: `root_cause_category`, `problem_description`, `fix_applied`, `prevention_steps`, `incident_start`, `incident_end`
- Live MTTR preview calculated client-side from the two timestamps before submission
- Submits `POST /incidents/{id}/rca`; on success redirects to detail view

### Styling

Dark engineering theme via `App.css`. Monospace font for signal payloads and state labels. No external UI framework — plain CSS with CSS variables for theming.

---

## 12. Attribution

All prompts and planning documents are checked into `prompts_log.md`.

| Contributor | Contribution |
|---|---|
| **Student (author)** | Entire Monitoring Service, `strategies.py`, `state_machine.py`, `rca.py`, architecture decisions, debugging, integration |
| Ex-Microsoft SRE | Two-service architecture recommendation, backpressure concept, RCA 3 W's framework |
| Claude (Anthropic) | Architecture validation, pattern guidance, boilerplate code, documentation |
| GPT-4 | Ingestion pipeline research |
