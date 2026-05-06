# incident_service/consumer.py
# Reads WorkItemCreated events from Redis Streams published by Monitoring Service

import asyncio
from redis.asyncio import from_url as redis_from_url
import json
import os

REDIS_URL      = os.getenv("REDIS_URL", "redis://localhost:6379")
INCIDENT_STREAM = "incidents:events"
GROUP_NAME     = "incident-workers"
CONSUMER_NAME  = "incident-worker-1"

async def start_event_consumer():
    """
    Listens to Redis Streams for WorkItemCreated events.
    When Monitoring Service creates a Work Item, this picks it up
    and makes the Incident Service aware of it.
    """
    r = await redis_from_url(REDIS_URL)

    # create consumer group if not exists
    try:
        await r.xgroup_create(INCIDENT_STREAM, GROUP_NAME, id="0", mkstream=True)
    except Exception:
        pass  # group already exists

    print("[CONSUMER] Incident event consumer started, listening...")

    while True:
        try:
            messages = await r.xreadgroup(
                GROUP_NAME, CONSUMER_NAME,
                {INCIDENT_STREAM: ">"},
                count=50, block=2000
            )

            if not messages:
                continue

            for stream, entries in messages:
                for msg_id, data in entries:
                    event = json.loads(data[b"data"])
                    await handle_event(event)
                    await r.xack(INCIDENT_STREAM, GROUP_NAME, msg_id)

        except Exception as e:
            print(f"[CONSUMER] Error: {e}, retrying in 2s...")
            await asyncio.sleep(2)

async def handle_event(event: dict):
    """Handle incoming events from Monitoring Service."""
    if event.get("event") == "WorkItemCreated":
        print(
            f"[CONSUMER] New Work Item: {event['work_item_id']} | "
            f"Component: {event['component_id']} | "
            f"Priority: {event['priority']}"
        )
        # Incident Service already has the Work Item in Postgres
        # (written by Monitoring Service's debounce worker)
        # This consumer just logs/alerts — extend here for notifications