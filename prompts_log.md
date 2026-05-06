# Prompts & AI Assistance Log

As required by the assignment submission guidelines, this file documents all AI
and external assistance used in building this project.

---

## 1. Ex-Microsoft SRE Consultation

**Source:** In-person conversation with an ex-Microsoft SRE (worked at Microsoft China)

**Contributions:**
- Recommended two-service architecture (Monitoring Service + Incident Service) for fault isolation
- Suggested OpenTelemetry SDK as the agent/SDK layer
- Recommended Apache Kafka / Redis Streams for the message queue layer
- Explained backpressure: "when downstream systems are slower than upstream systems"
- Gave the Event Viewer design:
  - Monitoring system takes events and converts to incidents
  - Incident system handles RCA with summary, priority, problem description, resolution steps, mitigation steps (3 W's)
  - Treat as two separate systems for fault tolerance
  - Create DB partitioned by P0/P1/P2 with UI

---

## 2. Claude (Anthropic) — Architecture & Code

**Model:** Claude Sonnet (claude.ai)

**Contributions:**
- Validated and extended the SRE's two-service architecture
- Designed the full system architecture diagram
- Selected tech stack (FastAPI, Redis Streams, MongoDB, PostgreSQL, TimescaleDB)
- Designed the Strategy Pattern for alerting (P0/P1/P2)
- Designed the State Machine Pattern for Work Item lifecycle
- Designed the Redis SETNX deduplication/debouncing logic
- Generated boilerplate and skeleton code for:
  - monitoring_service: main.py, buffer.py, debounce.py, publisher.py, metrics.py, gateway.py, rate_limiter.py
  - incident_service: main.py, consumer.py, rca.py, state_machine.py
  - shared: models.py
  - infrastructure: docker-compose.yml, db_init.sql, Dockerfile
  - frontend: App.jsx, App.css, LiveFeed.jsx, IncidentDetail.jsx, RCAForm.jsx
  - tests: state machine and RCA validation unit tests
- Wrote DESIGN.md and README.md documentation

**Author wrote independently:**
- strategies.py — Strategy pattern implementation (guided but written by author)
- state_machine.py — State machine logic (guided but written by author)
- Debug and integration work

---

## 3. GPT-4 — Ingestion Pipeline Research

**Contributions:**
- Research on ingestion pipeline protocols (HTTP/2, gRPC)
- OpenTelemetry transport mechanisms

---

## Key Design Decisions & Code Written Independently by Author

1. **Two-service split** — understood and validated independently after SRE explanation
2. **Redis Streams as fault boundary** — understood why Postgres/Mongo cannot be the bridge
3. **SETNX for deduplication** — understood the race condition problem and atomic solution
4. **Strategy vs if/elif** — understood why the pattern is better for maintainability
5. **State machine transition map** — understood why explicit maps beat nested conditionals

## Code Written Independently by Author

### Monitoring System (fully authored by student)
- `monitoring_system/main.py` — FastAPI app setup, signal ingestion endpoint, health endpoint
- `monitoring_system/gateway.py` — signal validation, component type checking
- `monitoring_system/rate_limiter.py` — token bucket rate limiter setup
- `monitoring_system/buffer.py` — Redis Streams producer logic
- `monitoring_system/debounce.py` — deduplication worker, Redis SETNX lock logic
- `monitoring_system/publisher.py` — WorkItemCreated event publisher
- `monitoring_system/metrics.py` — throughput printer background task
- `monitoring_system/strategies.py` — full Strategy pattern implementation
  (AlertStrategy ABC, APIStrategy, RDBMSStrategy, QueueStrategy, CacheStrategy,
  STRATEGY_MAP, get_alert function)

### Incident System (partially authored by student)
- `incident_system/state_machine.py` — State Machine pattern, transition validation,
  RCA blocking logic (VALID_TRANSITIONS map, transition function)
- `incident_system/rca.py` — RCA validation, MTTR calculation

### Understanding demonstrated through conversation
- Explained ABC and abstract methods independently
- Ranked component priorities (API → RDBMS → Queue → Cache) from own judgment
- Identified the race condition in deduplication without prompting
- Questioned the Redis Streams bridge independently
  ("should event publisher save to Postgres or Mongo?")
- Caught missing arrow between publisher and consumer in architecture diagram