# monitoring_system/rate_limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address

# Token bucket rate limiter — keyed by IP address
# 1000 requests per minute per IP
limiter = Limiter(key_func=get_remote_address, default_limits=["1000/minute"])