# monitoring_system/gateway.py
# Handles signal validation and pushes to Redis Streams buffer

from shared.models import Signal
from Monitoring_system.buffer import push_to_stream

async def handle_signal(signal: Signal) -> dict:
    """
    Validates the incoming signal and pushes it to Redis Streams.
    Returns immediately — never waits for DB write.
    This is what keeps the gateway alive under 10,000 signals/sec.
    """
    # validate component type is one we know about
    KNOWN_TYPES = {"API", "RDBMS", "CACHE", "QUEUE", "MCP", "NOSQL"}
    if signal.component_type not in KNOWN_TYPES:
        raise ValueError(f"Unknown component_type: {signal.component_type}. "
                         f"Must be one of {KNOWN_TYPES}")

    # push to Redis Streams buffer (non-blocking)
    await push_to_stream(signal.model_dump())

    return {
        "status":     "accepted",
        "signal_id":  signal.signal_id,
        "component":  signal.component_id,
        "priority":   _get_expected_priority(signal.component_type)
    }

def _get_expected_priority(component_type: str) -> str:
    """Quick priority hint in the response — actual priority set by debounce worker."""
    priority_map = {
        "API":    "P0",
        "RDBMS":  "P0",
        "MCP":    "P1",
        "NOSQL":  "P1",
        "QUEUE":  "P1",
        "CACHE":  "P2",
    }
    return priority_map.get(component_type, "P2")