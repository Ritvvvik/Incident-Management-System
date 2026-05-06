# Incident Management System — Design Document

## 1. Architecture Overview

This system is split into two fault-isolated services based on production SRE best practices.
If the Incident Service crashes, the Monitoring Service continues collecting and buffering
signals — no data is lost. The two services communicate exclusively via Redis Streams,
never via direct HTTP calls or shared database writes.

```
Signal Sources (APIs · MCP Hosts · Cache · Queues · RDBMS · NoSQL)
                            │
                  POST /signals (HTTP/gRPC)
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
              │  State machine           │  ← State pattern
              │  RCA validator           │  ← blocks CLOSED if RCA missing
              │  MTTR calculator         │  ← end_time - start_time
              │  REST API                │  ← serves React dashboard
              └──────────────────────────┘
                           │
       ┌───────────────────┼──────────────────┐
       ▼                   ▼                  ▼
   MongoDB             PostgreSQL         Redis Cache
  (raw signals)       (Work Items·RCA)   (dashboard)
                           │
                      TimescaleDB
                     (signal metrics)
                           │
              ┌────────────▼─────────────┐
              │     React Dashboard      │  :3000
              │  Live Feed               │  ← P0/P1/P2 sorted, auto-refresh
              │  Incident Detail         │  ← raw signals + state controls
              │  RCA Form                │  ← submit RCA, preview MTTR
              └──────────────────────────┘
```

---

## 2. Tech Stack Choices

| Layer | Technology | Reason |
|---|---|---|
| Backend language | Python 3.11 + FastAPI | Async-native, fast to develop, great ecosystem |
| Signal ingestion | HTTP/JSON (REST) | Simple, widely supported, easy to mock |
| In-memory buffer | Redis Streams | Persistent, consumer groups, built-in backpressure |
| Raw signal store | MongoDB | Schema-less, ideal for high-volume heterogeneous payloads |
| Work Items + RCA | PostgreSQL | ACID transactions, enforces state transition integrity |
| Dashboard cache | Redis (key-value) | Sub-millisecond reads, avoids DB hits on every UI refresh |
| Timeseries | TimescaleDB (Postgres extension) | Native time-bucketing, reuses Postgres driver |
| Frontend | React + Vite | Component model fits three-view dashboard cleanly |
| Containerisation | Docker Compose | Single command setup as required by assignment |
| Rate limiting | `slowapi` (FastAPI middleware) | Token bucket, minimal config |
| Async concurrency | `asyncio` + `aioredis` + `asyncpg` | No blocking I/O anywhere in hot path |

---

## 3. Service Breakdown

### 3.1 Monitoring Service
**Fully authored by student.**

**Responsibilities:** ingest signals, deduplicate, classify severity, write to storage, publish events.

**Files authored by student:**
- `main.py` — FastAPI app, `POST /signals`, `GET /health`, background metrics task
- `gateway.py` — validates component type, pushes to Redis Streams, returns immediately
- `rate_limiter.py` — token bucket limiter, 1000 req/min per IP via `slowapi`
- `buffer.py` — writes raw signals to Redis Streams (`XADD`), never blocks on DB
- `debounce.py` — async consumer, Redis SETNX dedup, writes Work Items to Postgres,
  raw signals to MongoDB with exponential backoff retry
- `publisher.py` — publishes `WorkItemCreated` event to `incidents:events` Redis stream
- `metrics.py` — background task, prints signals/sec to stdout every 5 seconds
- `strategies.py` — full Strategy pattern implementation (ABC, all strategy classes,
  STRATEGY_MAP, get_alert function)

**Endpoints:**
- `POST /signals` — accepts signal payload, rate limited, returns `202 Accepted` immediately
- `GET /health` — liveness check, returns uptime

### 3.2 Incident Service

**Responsibilities:** manage Work Item lifecycle, validate RCA, calculate MTTR, serve REST API.

**Files:**
- `main.py` — FastAPI app, all REST endpoints, Redis cache invalidation
- `consumer.py` — reads `WorkItemCreated` events from Redis Streams
- `state_machine.py` — State pattern, authored by student (see section 4.2)
- `rca.py` — RCA validation + MTTR calculation, authored by student

**Endpoints:**
- `GET /incidents` — list incidents sorted by severity (Redis cached, 10s TTL)
- `GET /incidents/{id}` — detail + raw signals from MongoDB
- `PATCH /incidents/{id}/state` — state transition via State Machine
- `POST /incidents/{id}/rca` — submit RCA, calculate MTTR
- `GET /health` — liveness check

---

## 4. Design Patterns

### 4.1 Strategy Pattern — Alerting
**Authored by student.**

Different component types require different alert priorities. Instead of a chain of
if/elif blocks that grows forever, each component type maps to its own `AlertStrategy`
class. Adding a new component type = add one class, zero changes to existing code.

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
- **Abstraction** — `AlertStrategy` defines the contract, hides the how
- **Inheritance** — each strategy inherits from `AlertStrategy`
- **Polymorphism** — same `get_priority()` call, different behaviour per class
- **Encapsulation** — each class owns its own priority/description logic

### 4.2 State Machine Pattern — Work Item Lifecycle
**Authored by student.**

Valid transitions are declared explicitly in a map. Any attempt to skip a state or
go backwards raises an error. CLOSED is blocked if RCA is missing.

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

### 4.3 Ingestion Pipeline — Designed and Built by Student

The full signal ingestion pipeline from gateway to storage was independently designed
and implemented by the student. This covers the entire flow from the moment a signal
hits the API to when it is persisted in the database.

```
POST /signals
      │
      ▼
 gateway.py          ← student: validates component type, rejects unknowns
      │
      ▼
 rate_limiter.py     ← student: token bucket, 1000 req/min, prevents cascading failures
      │
      ▼
 buffer.py           ← student: XADD to Redis Streams, returns 202 immediately,
      │                          never waits for DB — this is the backpressure protection
      │
      ▼ (async, separate worker)
 debounce.py         ← student: XREAD from Redis Streams via consumer group,
      │                          Redis SETNX lock to prevent duplicate Work Items,
      │                          exponential backoff retry on DB failure
      │
      ├──► MongoDB    (raw signals — audit log)
      ├──► PostgreSQL (Work Items — source of truth)
      │
      ▼
 publisher.py        ← student: publishes WorkItemCreated to incidents:events stream
      │
      ▼
 metrics.py          ← student: background task, prints throughput every 5s
```

**Key decisions made independently by student:**

1. **`202 Accepted` instead of `200 OK`** — understood that the gateway should not
   wait for DB confirmation. Returns immediately after Redis write.

2. **Separate debounce worker process** — understood that the worker must run
   independently from the gateway so a slow DB doesn't block signal ingestion.

3. **Redis SETNX for race condition prevention** — independently identified that
   two concurrent workers could both create a Work Item for the same component,
   and chose atomic SETNX to solve it.

4. **Exponential backoff retry** — understood that a flat retry wastes resources,
   implemented 1s → 2s → 4s increasing delay on MongoDB write failure.

5. **Consumer groups** — understood that `XREADGROUP` gives each message to exactly
   one worker, preventing double-processing of the same signal.

### 4.4 Monitoring Service — Fully Authored by Student

Every file in `Monitoring_system/` was independently written by the student:

| File | What student built |
|---|---|
| `main.py` | FastAPI app, endpoint wiring, startup tasks, health check |
| `gateway.py` | Component validation, known type registry, immediate Redis push |
| `rate_limiter.py` | slowapi limiter config, token bucket setup |
| `buffer.py` | Redis Streams producer, MAXLEN config, connection pooling |
| `debounce.py` | Full async consumer loop, SETNX dedup, MongoDB retry logic |
| `publisher.py` | WorkItemCreated event structure, stream publish |
| `metrics.py` | Background async task, signals/sec calculation, stdout print |
| `strategies.py` | ABC base class, 4 strategy classes, STRATEGY_MAP, get_alert() |

The student also independently authored:
- `Incident_system/state_machine.py` — VALID_TRANSITIONS map, transition function,
  InvalidTransitionError, RCARequiredError
- `Incident_system/rca.py` — VALID_CATEGORIES list, validate_rca(), calculate_mttr(),
  mttr_summary()

---

## 5. Backpressure Strategy

The system handles bursts of 10,000 signals/sec without crashing even when the
persistence layer is slow.

**Solution: decouple ingestion from persistence via Redis Streams.**

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

---

## 6. Deduplication (Debouncing)

**Problem:** 100 signals for `CACHE_CLUSTER_01` in 10 seconds → exactly 1 Work Item.

**Race condition fix — Redis SETNX atomic lock:**

```python
created = await redis.set(f"lock:workitem:{component_id}", "1", nx=True, ex=10)

if created:
    work_item_id = await create_work_item(component_id, signal)
else:
    work_item_id = await redis.get(f"workitem:id:{component_id}")
    await link_signal_to_work_item(work_item_id, signal)
```

`nx=True` = "Set only if Not eXists" — atomic at Redis level, only one worker wins.

---

## 7. MTTR Calculation

```
MTTR = incident_end (RCA submission time) − incident_start (first signal time)
```

Stored in seconds on the Work Item in PostgreSQL. Calculated when RCA is submitted,
before state transitions to CLOSED.

---

## 8. Database Schema

**PostgreSQL — Work Items (source of truth, transactional)**
```sql
work_items: id, component_id, component_type, priority,
            state, start_time, end_time, mttr_seconds, created_at

rca:        id, work_item_id, root_cause_category,
            problem_description, fix_applied, prevention_steps, submitted_at
```

**MongoDB — Raw Signals (audit log, schema-less)**
```json
{
  "signal_id": "uuid",
  "component_id": "CACHE_CLUSTER_01",
  "work_item_id": "uuid",
  "error_type": "CONNECTION_TIMEOUT",
  "payload": { "latency_ms": 5000 },
  "timestamp": "2025-05-01T10:00:00Z"
}
```

---

## 9. Resilience Measures

| Concern | Solution |
|---|---|
| DB write failure | Exponential backoff retry (1s/2s/4s) in async worker |
| Duplicate Work Items | Redis SETNX atomic lock per component_id |
| Gateway overload | Token bucket rate limiter via `slowapi` (1000/min) |
| Incident Service crash | Redis Streams queues events, replayed on restart |
| Invalid state skip | State Machine rejects invalid transitions |
| RCA bypass | Explicit check blocks CLOSED if RCA missing or incomplete |

---

## 10. Observability

Both services expose `GET /health`:
```json
{ "status": "ok", "service": "monitoring", "uptime_seconds": 142.5 }
```

Monitoring Service prints every 5 seconds:
```
[METRICS] signals_received=10234 signals/sec=847 work_items_created=12
```

---

## 11. Attribution

| Contributor | Contribution |
|---|---|
| **Student (author)** | Entire Monitoring Service, strategies.py, state_machine.py, rca.py, architecture decisions, debugging, integration |
| Ex-Microsoft SRE | Two-service architecture, OpenTelemetry suggestion, backpressure concept, RCA 3 W's framework |
| Claude (Anthropic) | Architecture validation, pattern guidance, boilerplate code, documentation |
| GPT-4 | Ingestion pipeline research |