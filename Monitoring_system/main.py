# Monitoring_system/main.py
import asyncio
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from shared.models import Signal
from Monitoring_system.gateway import handle_signal
from Monitoring_system.buffer import push_to_stream
from Monitoring_system.metrics import start_metrics_printer

# ── setup ───────────────────────────────────────────────────
limiter   = Limiter(key_func=get_remote_address)
START_TIME = time.time()

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(start_metrics_printer())
    yield

app = FastAPI(title="IMS Monitoring Service", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda r, e: HTTPException(429, "Rate limit exceeded"))
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── routes ──────────────────────────────────────────────────
@app.post("/signals", status_code=202)
@limiter.limit("1000/minute")
async def ingest_signal(signal: Signal, request: Request):
    """
    Accept a signal and push to Redis Streams immediately.
    Never waits for DB write — returns 202 instantly.
    """
    await push_to_stream(signal.model_dump())
    return {"status": "accepted", "signal_id": signal.signal_id}

@app.get("/health")
async def health():
    return {
        "status":         "ok",
        "service":        "monitoring",
        "uptime_seconds": round(time.time() - START_TIME, 2)
    }