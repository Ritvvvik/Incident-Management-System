# incident_service/main.py
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import asyncpg
from redis.asyncio import from_url as redis_from_url
import os
from datetime import datetime

from shared.models import RCA, StateTransitionRequest
from Incident_system.state_machine import transition, InvalidTransitionError, RCARequiredError
from Incident_system.rca import validate_rca, calculate_mttr, RCAValidationError
from Incident_system.consumer import start_event_consumer

POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://ims:ims@localhost:5433/ims")
REDIS_URL    = os.getenv("REDIS_URL",    "redis://localhost:6379")
MONGO_URL    = os.getenv("MONGO_URL",    "mongodb://localhost:27017")
START_TIME   = time.time()

pg = None
r  = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global pg, r
    pg = await asyncpg.connect(POSTGRES_URL)
    r  = await redis_from_url(REDIS_URL)
    asyncio.create_task(start_event_consumer())
    yield
    await pg.close()
    await r.close()

app = FastAPI(title="IMS Incident Service", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── GET /incidents ─────────────────────────────────────────
@app.get("/incidents")
async def list_incidents():
    """Returns all incidents sorted by severity (P0 first)."""
    # try cache first
    cached = await r.get("dashboard:incidents")
    if cached:
        import json
        return json.loads(cached)

    rows = await pg.fetch("""
        SELECT * FROM work_items
        ORDER BY
            CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,
            start_time DESC
    """)
    incidents = [dict(r) for r in rows]

    # cache for 10 seconds
    import json
    await r.set("dashboard:incidents", json.dumps(incidents, default=str), ex=10)
    return incidents

# ── GET /incidents/:id ─────────────────────────────────────
@app.get("/incidents/{incident_id}")
async def get_incident(incident_id: str):
    """Returns incident detail + raw signals from MongoDB."""
    row = await pg.fetchrow("SELECT * FROM work_items WHERE id=$1", incident_id)
    if not row:
        raise HTTPException(404, "Incident not found")

    # fetch raw signals from MongoDB
    from motor.motor_asyncio import AsyncIOMotorClient
    client = AsyncIOMotorClient(MONGO_URL)
    signals = await client.ims.signals.find(
        {"work_item_id": incident_id}
    ).to_list(length=500)
    for s in signals:
        s.pop("_id", None)

    return {"incident": dict(row), "signals": signals}

# ── PATCH /incidents/:id/state ─────────────────────────────
@app.patch("/incidents/{incident_id}/state")
async def update_state(incident_id: str, body: StateTransitionRequest):
    """Transition incident state using the state machine."""
    row = await pg.fetchrow("SELECT * FROM work_items WHERE id=$1", incident_id)
    if not row:
        raise HTTPException(404, "Incident not found")

    # check if RCA exists
    rca_row  = await pg.fetchrow("SELECT id FROM rca WHERE work_item_id=$1", incident_id)
    has_rca  = rca_row is not None

    try:
        new_state = transition(row["state"], body.new_state, has_rca)
    except InvalidTransitionError as e:
        raise HTTPException(400, str(e))
    except RCARequiredError as e:
        raise HTTPException(422, str(e))

    await pg.execute(
        "UPDATE work_items SET state=$1 WHERE id=$2",
        new_state, incident_id
    )

    # invalidate cache
    await r.delete("dashboard:incidents")
    return {"incident_id": incident_id, "new_state": new_state}

# ── POST /incidents/:id/rca ────────────────────────────────
@app.post("/incidents/{incident_id}/rca")
async def submit_rca(incident_id: str, body: RCA):
    """Submit RCA and calculate MTTR."""
    row = await pg.fetchrow("SELECT * FROM work_items WHERE id=$1", incident_id)
    if not row:
        raise HTTPException(404, "Incident not found")

    if row["state"] == "CLOSED":
        raise HTTPException(400, "Incident already closed")

    # validate RCA FIRST — before touching the database
    try:
        validate_rca(body)
    except RCAValidationError as e:
        raise HTTPException(422, str(e))

    # calculate MTTR
    mttr_seconds = calculate_mttr(body.incident_start, body.incident_end)

    async with pg.transaction():
        await pg.execute("""
            INSERT INTO rca (id, work_item_id, root_cause_category,
                             problem_description, fix_applied, prevention_steps, submitted_at)
            VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, NOW())
        """, incident_id, body.root_cause_category,
             body.problem_description, body.fix_applied, body.prevention_steps)

        await pg.execute("""
            UPDATE work_items SET end_time=$1, mttr_seconds=$2 WHERE id=$3
        """, body.incident_end, mttr_seconds, incident_id)

    await r.delete("dashboard:incidents")
    return {
        "status":       "rca_submitted",
        "mttr_seconds": mttr_seconds,
        "mttr_minutes": round(mttr_seconds / 60, 2)
        }                  

# ── GET /health ────────────────────────────────────────────
@app.get("/health")
async def health():
    return {
        "status":         "ok",
        "service":        "incident",
        "uptime_seconds": round(time.time() - START_TIME, 2)
    }