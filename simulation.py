"""
simulate_failure.py
Mocks realistic failure cascades to test the IMS system.

Usage:
  python simulate_failure.py --scenario rdbms_outage
  python simulate_failure.py --scenario burst --component CACHE_CLUSTER_01 --count 200
  python simulate_failure.py --scenario full_cascade
"""
import asyncio
import httpx
import argparse
import uuid
from datetime import datetime

MONITORING_URL = "http://localhost:8000"

def make_signal(component_id: str, component_type: str, error_type: str, payload: dict) -> dict:
    return {
        "signal_id":      str(uuid.uuid4()),
        "component_id":   component_id,
        "component_type": component_type,
        "error_type":     error_type,
        "payload":        payload,
        "timestamp":      datetime.utcnow().isoformat()
    }

async def send_signal(client: httpx.AsyncClient, signal: dict):
    try:
        r = await client.post(f"{MONITORING_URL}/signals", json=signal)
        print(f"  → {signal['component_id']} [{signal['component_type']}] — {r.status_code}")
    except Exception as e:
        print(f"  → ERROR: {e}")

async def scenario_rdbms_outage(client):
    print("\n[SCENARIO] RDBMS Outage")
    for i in range(5):
        await send_signal(client, make_signal(
            "RDBMS_PRIMARY_01", "RDBMS", "CONNECTION_TIMEOUT",
            {"latency_ms": 9000 + i * 100, "host": "db-primary", "attempt": i}
        ))
        await asyncio.sleep(0.5)

async def scenario_burst(client, component: str, count: int):
    print(f"\n[SCENARIO] Burst — {count} signals for {component}")
    tasks = [
        send_signal(client, make_signal(
            component, "CACHE", "CONNECTION_REFUSED",
            {"node": f"redis-{i % 3}", "attempt": i}
        ))
        for i in range(count)
    ]
    await asyncio.gather(*tasks)
    print(f"  → Sent {count} signals. Should create exactly 1 Work Item.")

async def scenario_full_cascade(client):
    print("\n[SCENARIO] Full Cascade — RDBMS outage → MCP failure")

    # Step 1: RDBMS starts failing
    print("\nStep 1: RDBMS failure (P0)")
    for i in range(10):
        await send_signal(client, make_signal(
            "RDBMS_PRIMARY_01", "RDBMS", "CONNECTION_TIMEOUT",
            {"latency_ms": 9000, "host": "db-primary"}
        ))
    await asyncio.sleep(2)

    # Step 2: MCP Host starts failing
    print("\nStep 2: MCP Host failure (P1)")
    for i in range(5):
        await send_signal(client, make_signal(
            "MCP_HOST_02", "MCP", "HEALTH_CHECK_FAILED",
            {"host": "mcp-02", "last_seen": "30s ago"}
        ))
    await asyncio.sleep(2)

    # Step 3: Cache starts degrading
    print("\nStep 3: Cache degraded (P2)")
    for i in range(8):
        await send_signal(client, make_signal(
            "CACHE_CLUSTER_01", "CACHE", "HIGH_LATENCY",
            {"latency_ms": 800 + i * 50, "node": "redis-1"}
        ))

    print("\n[DONE] Check your dashboard at http://localhost:3000")

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["rdbms_outage", "burst", "full_cascade"],
                        default="full_cascade")
    parser.add_argument("--component", default="CACHE_CLUSTER_01")
    parser.add_argument("--count", type=int, default=200)
    args = parser.parse_args()

    async with httpx.AsyncClient(timeout=10) as client:
        if args.scenario == "rdbms_outage":
            await scenario_rdbms_outage(client)
        elif args.scenario == "burst":
            await scenario_burst(client, args.component, args.count)
        elif args.scenario == "full_cascade":
            await scenario_full_cascade(client)

if __name__ == "__main__":
    asyncio.run(main())