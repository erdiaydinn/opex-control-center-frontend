"""Small production-shape PostgreSQL concurrency gate for pilot branches."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import os
from statistics import quantiles
from time import perf_counter

import psycopg


database_url = os.environ["DATABASE_URL"]
tenant_id = os.environ["WORKFORCE_TENANT_ID"]
operations = max(100, int(os.getenv("WORKFORCE_LOAD_OPERATIONS", "500")))
workers = max(4, int(os.getenv("WORKFORCE_LOAD_WORKERS", "24")))


def read_truth(_: int) -> float:
    started = perf_counter()
    with psycopg.connect(database_url) as database, database.cursor() as cursor:
        cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", (tenant_id,))
        cursor.execute(
            """SELECT
                 (SELECT count(*) FROM workforce_entities),
                 (SELECT count(*) FROM recruitment_requests),
                 (SELECT count(*) FROM workforce_notification_outbox)"""
        )
        cursor.fetchone()
    return (perf_counter() - started) * 1000


latencies: list[float] = []
with ThreadPoolExecutor(max_workers=workers) as pool:
    futures = [pool.submit(read_truth, index) for index in range(operations)]
    for future in as_completed(futures):
        latencies.append(future.result())

p95 = quantiles(latencies, n=100)[94]
maximum = max(latencies)
if len(latencies) != operations or p95 > 5000:
    raise SystemExit(f"PostgreSQL load gate failed: completed={len(latencies)}/{operations} p95_ms={p95:.1f}")
print(f"PostgreSQL load gate passed: operations={operations} workers={workers} p95_ms={p95:.1f} max_ms={maximum:.1f}")
