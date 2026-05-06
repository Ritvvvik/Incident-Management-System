# publisher.py — publishes WorkItemCreated event to Redis Streams
import json
from datetime import datetime

INCIDENT_STREAM = "incidents:events"

async def publish_work_item_created(r, work_item_id: str, component_id: str, priority: str):
    """Publishes event so Incident Service knows a new Work Item exists."""
    await r.xadd(INCIDENT_STREAM, {
        "data": json.dumps({
            "event":         "WorkItemCreated",
            "work_item_id":  work_item_id,
            "component_id":  component_id,
            "priority":      priority,
            "created_at":    datetime.utcnow().isoformat()
        })
    })