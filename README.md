# Incident Management System (IMS)

A production-grade, resilient Incident Management System built to monitor distributed
stacks and manage failure mediation workflows. Built with Python (FastAPI), Redis,
PostgreSQL, MongoDB and React.

---

## Architecture Diagram

```
Signal Sources (APIs · MCP Hosts · Cache · Queues · RDBMS · NoSQL)
                            │
                  POST /signals (HTTP)
                            │
              ┌─────────────▼────────────┐
              │    Monitoring Service    │  :8000
              │  Rate limiter            │  ← 1000 req/min
              │  Redis Streams buffer    │  ← backpressure layer
              │  Debounce worker         │  ← Redis SETNX dedup
              │  Alert Strategy engine   │  ← P0 / P1 / P2
              │  Event publisher         │  ← WorkItemCreated
              └────────────┬─────────────┘
                           │
                    Redis Streams
                  (fault boundary)
                           │
              ┌────────────▼─────────────┐
              │    Incident Service      │  :8001
              │  State Machine           │  ← OPEN→INVESTIGATING→RESOLVED→CLOSED
              │  RCA Validator           │  ← blocks CLOSED if RCA missing
              │  MTTR Calculator         │
              │  REST API                │
              └────────────┬─────────────┘
                           │
         ┌─────────────────┼──────────────────┐
         ▼                 ▼                  ▼
     MongoDB           PostgreSQL        Redis Cache
   (raw signals)     (Work Items·RCA)   (dashboard)
                           │
                      TimescaleDB
                     (aggregations)
                           │
              ┌────────────▼─────────────┐
              │     React Dashboard      │  :3000
              │  Live Feed               │
              │  Incident Detail         │
              │  RCA Form                │
              └──────────────────────────┘
```

---

## Quick Start

### Prerequisites
- Docker Desktop installed and running
- Node.js 18+ (for frontend)
- Python 3.11+ with conda or venv

### 1. Start all databases

```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
docker run -d --name mongo -p 27017:27017 mongo:7
docker run -d --name postgres -e POSTGRES_USER=ims -e POSTGRES_PASSWORD=ims -e POSTGRES_DB=ims -p 5432:5432 timescale/timescaledb:latest-pg15
```

### 2. Load database schema

```bash
docker exec -i postgres psql -U ims -d ims < db_init.sql
```

### 3. Install Python dependencies

```bash
conda create -n ims python=3.11
conda activate ims
pip install fastapi uvicorn pydantic asyncpg aioredis motor slowapi python-multipart httpx
```

### 4. Run Monitoring Service

```bash
cd Monitoring_system
uvicorn main:app --port 8000 --reload
```

### 5. Run Incident Service

```bash
cd Incident_system
uvicorn main:app --port 8001 --reload
```

### 6. Run React Dashboard

```bash
cd Frontend
npm install
npm run dev
```

Open http://localhost:3000

### Or run everything with Docker Compose

```bash
docker-compose up --build
```

---

## Project Structure

```
IMS/
├── Monitoring_system/       ← authored by student
│   ├── main.py              # FastAPI app, /signals, /health
│   ├── gateway.py           # Signal validation, component type check
│   ├── rate_limiter.py      # Token bucket, 1000/min per IP
│   ├── buffer.py            # Redis Streams producer (XADD)
│   ├── debounce.py          # Dedup worker, Redis SETNX, backoff retry
│   ├── publisher.py         # Publishes WorkItemCreated event
│   ├── metrics.py           # Prints signals/sec every 5s
│   └── strategies.py        # Strategy pattern — P0/P1/P2 alerting
│
├── Incident_system/
│   ├── main.py              # REST API (5 endpoints)
│   ├── consumer.py          # Redis Streams event consumer
│   ├── state_machine.py     # State pattern — OPEN→CLOSED  [student]
│   ├── rca.py               # RCA validation + MTTR         [student]
│
├── shared/
│   └── models.py            # Pydantic schemas (Signal, WorkItem, RCA)
│
├── Frontend/
│   ├── src/
│   │   ├── App.jsx          # Routing
│   │   ├── App.css          # Dark engineering theme
│   │   ├── main.jsx         # React entry point
│   │   └── pages/
│   │       ├── LiveFeed.jsx        # P0/P1/P2 sorted, auto-refresh 5s
│   │       ├── IncidentDetail.jsx  # Raw signals + state transitions
│   │       └── RCAForm.jsx         # RCA form + MTTR preview
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── tests/
│   └── tests.py             # Unit tests — state machine + RCA validation
│
├── docs/
│   └── prompts/
│       └── prompts_log.md   # AI assistance attribution (required)
│
├── db_init.sql              # PostgreSQL schema
├── docker-compose.yml       # Full stack in one command
├── Dockerfile               # Backend services
├── requirements.txt
├── simulation.py            # Failure simulation script
├── DESIGN.md                # Full architecture + design decisions
└── README.md
```

---

## API Reference

### Monitoring Service (:8000)

| Method | Endpoint | Description |
|---|---|---|
| POST | `/signals` | Ingest signal (rate limited: 1000/min) |
| GET | `/health` | Liveness check |

**Signal payload:**
```json
{
  "component_id":   "CACHE_CLUSTER_01",
  "component_type": "CACHE",
  "error_type":     "CONNECTION_TIMEOUT",
  "payload":        { "latency_ms": 5000, "node": "redis-3" },
  "timestamp":      "2025-05-01T10:00:00Z"
}
```

### Incident Service (:8001)

| Method | Endpoint | Description |
|---|---|---|
| GET | `/incidents` | List incidents sorted by severity |
| GET | `/incidents/{id}` | Incident detail + raw signals from MongoDB |
| PATCH | `/incidents/{id}/state` | Transition state via State Machine |
| POST | `/incidents/{id}/rca` | Submit RCA + calculate MTTR |
| GET | `/health` | Liveness check |

**State transition:**
```json
{ "new_state": "INVESTIGATING" }
```

**RCA payload:**
```json
{
  "root_cause_category": "Infrastructure",
  "problem_description": "Redis node ran out of memory",
  "fix_applied":         "Restarted node, set eviction policy",
  "prevention_steps":    "Add memory alerting at 70%",
  "incident_start":      "2025-05-01T10:00:00Z",
  "incident_end":        "2025-05-01T10:45:00Z"
}
```

---

## How Backpressure is Handled

The ingestion gateway **never blocks on a database write.**

1. `POST /signals` writes the signal to Redis Streams and returns `202 Accepted` immediately
2. Debounce Worker reads from Redis Streams at its own pace
3. If MongoDB is slow, signals queue in Redis Streams (bounded by `MAXLEN 100,000`)
4. Worker uses exponential backoff retry (1s → 2s → 4s) on failure
5. Redis Streams persist to disk — no data loss on Redis restart

This decoupling means the gateway handles 10,000+ signals/sec regardless of DB latency.

---

## Design Patterns

**Strategy Pattern** — `Monitoring_system/strategies.py`
Each component type maps to an `AlertStrategy` class returning P0/P1/P2.
Adding a new component = add one class, zero changes to existing code.

**State Machine Pattern** — `Incident_system/state_machine.py`
Transitions declared in an explicit map. Rejects invalid transitions and blocks
CLOSED if RCA is missing or incomplete.

---

## Running Tests

```bash
conda activate ims
cd IMS
pytest tests/tests.py -v
```

Tests cover:
- Valid and invalid state machine transitions
- Cannot skip states, cannot go backwards
- Cannot close without RCA
- RCA field validation
- MTTR calculation accuracy

---

## Failure Simulation

```bash
# Simulate RDBMS outage
python simulation.py --scenario rdbms_outage

# Burst test — 200 signals → should create exactly 1 Work Item
python simulation.py --scenario burst --component CACHE_CLUSTER_01 --count 200

# Full cascade — RDBMS → MCP → Cache failure
python simulation.py --scenario full_cascade
```

---

## Attribution

This project was built with the following assistance as permitted by assignment guidelines.
All prompts, plans and design documents are checked into `docs/prompts/`.

| Contributor | Role |
|---|---|
| **Student (author)** | Entire Monitoring Service, strategies.py, state_machine.py, rca.py, architecture decisions, debugging |
| Ex-Microsoft SRE | Two-service split recommendation, backpressure concept, RCA 3 W's framework |
| Claude (Anthropic) | Architecture validation, pattern guidance, boilerplate, documentation |
| GPT-4 | Ingestion pipeline research |