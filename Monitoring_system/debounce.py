# debounce.py — reads from Redis Streams, deduplicates signals into Work Items
import asyncio
from redis.asyncio import from_url as redis_from_url
import asyncpg
import json
import os
import uuid
from datetime import datetime

from Monitoring_system.strategies import get_alert
from Monitoring_system.publisher import publish_work_item_created

REDIS_URL   = os.getenv("REDIS_URL", "redis://localhost:6379")
POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql://ims:ims@localhost:5433/ims")
STREAM_NAME  = "signals:raw"
GROUP_NAME   = "debounce-workers"
CONSUMER_NAME = "worker-1"
DEBOUNCE_WINDOW = 10  # seconds

# signals received counter for metrics
signals_received = 0

async def run_debounce_worker():
    """
    Reads signals from Redis Streams and deduplicates them.
    100 signals for same component within 10s → 1 Work Item
    """
    r = await redis_from_url(REDIS_URL)
    pg = await asyncpg.connect(POSTGRES_URL)

    # create consumer group if not exists
    try:
        await r.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
    except Exception:
        pass  # group already exists

    while True:
        messages = await r.xreadgroup(
            GROUP_NAME, CONSUMER_NAME,
            {STREAM_NAME: ">"},
            count=100, block=1000
        )

        if not messages:
            continue

        for stream, entries in messages:
            for msg_id, data in entries:
                global signals_received
                signals_received += 1

                signal = json.loads(data[b"data"])
                await process_signal(r, pg, signal, msg_id)

async def process_signal(r, pg, signal: dict, msg_id):
    component_id   = signal["component_id"]
    component_type = signal["component_type"]
    lock_key       = f"lock:workitem:{component_id}"
    work_item_key  = f"workitem:id:{component_id}"

    # atomic dedup — only one worker wins this lock
    created = await r.set(lock_key, "1", nx=True, ex=DEBOUNCE_WINDOW)

    if created:
        # this worker won — create Work Item in Postgres
        priority, description = get_alert(component_type)
        work_item_id = str(uuid.uuid4())

        await pg.execute("""
            INSERT INTO work_items (id, component_id, component_type, priority, state, start_time)
            VALUES ($1, $2, $3, $4, 'OPEN', $5)
        """, work_item_id, component_id, component_type, priority, datetime.utcnow())

        await r.set(work_item_key, work_item_id)

        # publish event for Incident Service
        await publish_work_item_created(r, work_item_id, component_id, priority)
    else:
        # Work Item already exists — just link signal
        work_item_id = (await r.get(work_item_key) or b"").decode()

    # save raw signal to MongoDB (fire and forget)
    asyncio.create_task(save_signal_to_mongo(signal, work_item_id))

    # acknowledge message
    await r.xack(STREAM_NAME, GROUP_NAME, msg_id)

async def save_signal_to_mongo(signal: dict, work_item_id: str):
    """Save raw signal to MongoDB audit log with retry."""
    from motor.motor_asyncio import AsyncIOMotorClient
    import os
    client = AsyncIOMotorClient(os.getenv("MONGO_URL", "mongodb://localhost:27017"))
    db = client.ims
    signal["work_item_id"] = work_item_id
    for attempt in range(3):
        try:
            await db.signals.insert_one(signal)
            return
        except Exception as e:
            await asyncio.sleep(2 ** attempt)  # exponential backoff: 1s, 2s, 4s