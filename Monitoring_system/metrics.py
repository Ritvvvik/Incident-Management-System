# metrics.py — prints throughput every 5 seconds
import asyncio
import time
from Monitoring_system import debounce # to read signals_received counter

async def start_metrics_printer():
    last_count = 0
    last_time  = time.time()

    while True:
        await asyncio.sleep(5)
        now          = time.time()
        current      = debounce.signals_received
        delta        = current - last_count
        elapsed      = now - last_time
        rate         = round(delta / elapsed, 1)
        last_count   = current
        last_time    = now
        print(f"[METRICS] signals_received={current} signals/sec={rate}")