# buffer.py — writes signals to Redis Streams (backpressure layer)
from redis.asyncio import from_url as redis_from_url
import json
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STREAM_NAME = "signals:raw"
MAX_LEN = 100_000  # max signals in stream before oldest are dropped

_redis = None

async def get_redis():
    global _redis
    if _redis is None:
        _redis = await redis_from_url(REDIS_URL)
    return _redis

async def push_to_stream(signal: dict):
    """Push raw signal to Redis Streams. Returns immediately."""
    r = await get_redis()
    await r.xadd(
        STREAM_NAME,
        {"data": json.dumps(signal, default=str)},
        maxlen=MAX_LEN,
        approximate=True
    )