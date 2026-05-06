# Incident Management System (IMS)

A production-grade, resilient Incident Management System built to monitor distributed
stacks and manage failure mediation workflows. Built with Python (FastAPI), Redis,
PostgreSQL, MongoDB and React.

---

## Table of Contents
 
- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Design Patterns](#design-patterns)
- [Backpressure & Resilience](#backpressure--resilience)
- [Running Tests](#running-tests)
- [Failure Simulation](#failure-simulation)
- [Attribution](#attribution)
---
 
## Overview
 
The Incident Management System (IMS) ingests signals from distributed infrastructure components (APIs, caches, queues, RDBMS, NoSQL), classifies them by severity, deduplicates bursts, and manages the full incident lifecycle — from detection through root cause analysis (RCA) and closure.
 
**Key capabilities:**
 
- Ingest up to 10,000+ signals/sec without blocking on database writes
- Automatic severity classification (P0 / P1 / P2) using the Strategy pattern
- Burst deduplication — 100 signals for the same component → exactly 1 Work Item
- Enforced state machine: `OPEN → INVESTIGATING → RESOLVED → CLOSED`
- RCA submission with automatic MTTR calculation
- Live React dashboard with auto-refresh every 5 seconds
---
 
## Architecture
 
```
Signal Sources (APIs · MCP Hosts · Cache · Queues · RDBMS · NoSQL)
                            │
                  POST /signals (HTTP)
                            │
              ┌─────────────▼────────────┐
              │    Monitoring Service    │  :8000
              │  Rate limiter            │  ← 1000 req/min per IP
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
 
The two services communicate **exclusively via Redis Streams** — never via direct HTTP or shared DB writes. If the Incident Service crashes, the Monitoring Service continues buffering signals with zero data loss.
 
---
 
## Tech Stack
 
| Layer | Technology | Reason |
|---|---|---|
| Backend | Python 3.11 + FastAPI | Async-native, fast, great ecosystem |
| Signal buffer | Redis Streams | Persistent, consumer groups, built-in backpressure |
| Raw signals | MongoDB | Schema-less, ideal for high-volume heterogeneous payloads |
| Work Items + RCA | PostgreSQL + TimescaleDB | ACID transactions, native time-bucketing |
| Dashboard cache | Redis (key-value) | Sub-millisecond reads, avoids DB hits on every UI refresh |
| Frontend | React + Vite | Clean component model for three-view dashboard |
| Containerisation | Docker Compose | Single-command full stack setup |
| Rate limiting | `slowapi` | Token bucket, minimal config |
| Async I/O | `asyncio` + `aioredis` + `asyncpg` | No blocking I/O in the hot path |
 
---
 
## Project Structure
 
```
IMS/
├── Monitoring_system/
│   ├── main.py              # FastAPI app — /signals, /health
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
│   ├── state_machine.py     # State pattern — OPEN→CLOSED
│   └── rca.py               # RCA validation + MTTR
│
├── shared/
│   └── models.py            # Pydantic schemas (Signal, WorkItem, RCA)
│
├── Frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css          # Dark engineering theme
│   │   ├── main.jsx
│   │   └── pages/
│   │       ├── LiveFeed.jsx         # P0/P1/P2 sorted, auto-refresh 5s
│   │       ├── IncidentDetail.jsx   # Raw signals + state transitions
│   │       └── RCAForm.jsx          # RCA form + MTTR preview
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
│
├── tests/
│   └── tests.py             # Unit tests — state machine + RCA
│
├── db_init.sql              # PostgreSQL schema
├── docker-compose.yaml      # Full stack in one command
├── Dockerfile               # Backend services
├── requirements.txt
├── simulation.py            # Failure simulation script
├── Design.md                # Architecture + design decisions
└── README.md
```
 
---
 
## Quick Start
 
### Prerequisites
 
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Node.js 18+
- Python 3.11+ with `conda` or `venv`
---
 
### Option A — Docker Compose (Recommended)
 
```bash
docker-compose up --build
```
 
Then open **http://localhost:3000**
 
---
 
### Option B — Manual Setup
 
#### 1. Start all databases
 
```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
docker run -d --name mongo -p 27017:27017 mongo:7
docker run -d --name postgres \
  -e POSTGRES_USER=ims \
  -e POSTGRES_PASSWORD=ims \
  -e POSTGRES_DB=ims \
  -p 5432:5432 timescale/timescaledb:latest-pg15
```
 
#### 2. Load database schema
 
```bash
docker exec -i postgres psql -U ims -d ims < db_init.sql
```
 
#### 3. Install Python dependencies
 
```bash
conda create -n ims python=3.11
conda activate ims
pip install -r requirements.txt
```
 
#### 4. Start the Monitoring Service
 
```bash
cd Monitoring_system
uvicorn main:app --port 8000 --reload
```
 
#### 5. Start the Incident Service
 
```bash
cd Incident_system
uvicorn main:app --port 8001 --reload
```
 
#### 6. Start the React Dashboard
 
```bash
cd Frontend
npm install
npm run dev
```
 
Open **http://localhost:3000**
 
---
 
## API Reference
 
### Monitoring Service — `:8000`
 
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/signals` | Ingest a signal (rate limited: 1000/min) |
| `GET` | `/health` | Liveness check |
 
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
 
Supported `component_type` values: `API`, `RDBMS`, `CACHE`, `QUEUE`, `MCP_HOST`, `NOSQL`
 
---
 
### Incident Service — `:8001`
 
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/incidents` | List all incidents sorted by severity |
| `GET` | `/incidents/{id}` | Incident detail + raw signals from MongoDB |
| `PATCH` | `/incidents/{id}/state` | Transition state via the State Machine |
| `POST` | `/incidents/{id}/rca` | Submit RCA + auto-calculate MTTR |
| `GET` | `/health` | Liveness check |
 
**State transition payload:**
 
```json
{ "new_state": "INVESTIGATING" }
```
 
Valid transitions: `OPEN → INVESTIGATING → RESOLVED → CLOSED`
> ⚠️ CLOSED is blocked until an RCA has been submitted.
 
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
 
## Design Patterns
 
### Strategy Pattern — `Monitoring_system/strategies.py`
 
Each component type maps to its own `AlertStrategy` class that returns a P0/P1/P2 priority. Adding a new component type requires adding one class with zero changes to existing code.
 
```python
class RDBMSStrategy(AlertStrategy):
    def get_priority(self) -> str:    return "P0"
    def get_description(self) -> str: return "RDBMS Failure"
 
class CacheStrategy(AlertStrategy):
    def get_priority(self) -> str:    return "P2"
    def get_description(self) -> str: return "Cache Failure"
```
 
**OOP concepts:** Abstraction · Inheritance · Polymorphism · Encapsulation
 
---
 
### State Machine Pattern — `Incident_system/state_machine.py`
 
Valid transitions are declared in an explicit map. Invalid transitions and attempts to close without an RCA are rejected at the function level.
 
```python
VALID_TRANSITIONS = {
    "OPEN":          {"INVESTIGATING"},
    "INVESTIGATING": {"RESOLVED"},
    "RESOLVED":      {"CLOSED"},
    "CLOSED":        set()
}
```
 
---
 
## Backpressure & Resilience
 
The gateway **never blocks on a database write**.
 
```
POST /signals → XADD to Redis Streams → 202 Accepted (immediate)
                        ↓
             Debounce worker (async)
                        ↓
              MongoDB + PostgreSQL
```
 
| Concern | Solution |
|---|---|
| DB write failure | Exponential backoff retry: 1s → 2s → 4s |
| Duplicate Work Items | Redis `SETNX` atomic lock per `component_id` |
| Gateway overload | Token bucket rate limiter (1000 req/min) |
| Incident Service crash | Redis Streams queues events; replayed on restart |
| Invalid state skip | State Machine rejects illegal transitions |
| Closing without RCA | Explicit check blocks `CLOSED` state |
| Data loss on restart | Redis Streams persist to disk (`MAXLEN 100,000`) |
 
---
 
## Running Tests
 
```bash
conda activate ims
pytest tests/tests.py -v
```
 
Tests cover valid and invalid state machine transitions, skipping states, going backwards, closing without RCA, RCA field validation, and MTTR calculation accuracy.
 
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
 
All AI-assisted prompts and design decisions are logged in [`prompts_log.md`](./prompts_log.md).
 
| Contributor | Role |
|---|---|
| **Student (author)** | Entire Monitoring Service, `strategies.py`, `state_machine.py`, `rca.py`, architecture decisions, debugging |
| Ex-Microsoft SRE | Two-service split recommendation, backpressure concept, RCA 3 W's framework |
| Claude (Anthropic) | Architecture validation, pattern guidance, boilerplate, documentation |
| GPT-4 | Ingestion pipeline research |
