import json
import os
import platform
import uuid
from pathlib import Path

from locust import HttpUser, between, events, task

from data import cleanup, setup

CORE_URL = os.getenv("CORE_URL", "http://api:8000")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://inventory-api:8001")
ORDERS_URL = os.getenv("ORDERS_URL", "http://orders-api:8002")
RUN_ID = os.getenv("LOAD_RUN_ID", uuid.uuid4().hex[:10])
RESULTS_DIR = Path(os.getenv("RESULTS_DIR", "/results"))
PRODUCT_ID = ""
SERVER_ERRORS = 0
LOCUST_EXCEPTIONS = 0


@events.test_start.add_listener
def prepare_data(environment, **kwargs) -> None:
    global PRODUCT_ID
    PRODUCT_ID = setup(RUN_ID)


@events.request.add_listener
def count_server_errors(response=None, **kwargs) -> None:
    global SERVER_ERRORS
    if response is not None and response.status_code >= 500:
        SERVER_ERRORS += 1


@events.user_error.add_listener
def count_locust_exceptions(**kwargs) -> None:
    global LOCUST_EXCEPTIONS
    LOCUST_EXCEPTIONS += 1


@events.test_stop.add_listener
def remove_data(environment, **kwargs) -> None:
    cleanup()


@events.quitting.add_listener
def write_summary_and_apply_guardrails(environment, **kwargs) -> None:
    total = environment.stats.total
    read_entries = [
        entry for (name, _method), entry in environment.stats.entries.items() if name.startswith("[read]")
    ]
    read_requests = sum(entry.num_requests for entry in read_entries)
    read_p95 = max(
        (entry.get_response_time_percentile(0.95) or 0 for entry in read_entries), default=0
    )
    summary = {
        "run_id": RUN_ID,
        "requests": total.num_requests,
        "failures": total.num_failures,
        "failure_ratio": total.fail_ratio,
        "requests_per_second": total.total_rps,
        "median_response_time_ms": total.median_response_time or 0,
        "p95_response_time_ms": total.get_response_time_percentile(0.95) or 0,
        "read_requests": read_requests,
        "read_p95_response_time_ms": read_p95,
        "server_errors": SERVER_ERRORS,
        "locust_exceptions": LOCUST_EXCEPTIONS,
        "python": platform.python_version(),
        "locust": environment.parsed_options.locustfile and "2.46.5",
        "users": environment.parsed_options.num_users,
        "spawn_rate": environment.parsed_options.spawn_rate,
        "run_time": str(environment.parsed_options.run_time),
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
    )
    (RESULTS_DIR / "environment.json").write_text(
        json.dumps(
            {
                "core_url": CORE_URL,
                "inventory_url": INVENTORY_URL,
                "orders_url": ORDERS_URL,
                "guardrails": {
                    "max_failure_ratio": float(os.getenv("MAX_FAILURE_RATIO", "0.01")),
                    "max_p95_ms": int(os.getenv("MAX_P95_MS", "1500")),
                    "max_read_p95_ms": int(os.getenv("MAX_READ_P95_MS", "1000")),
                    "min_requests": int(os.getenv("MIN_REQUESTS", "500")),
                },
                "locust": "2.46.5",
                "python": platform.python_version(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    min_requests = int(os.getenv("MIN_REQUESTS", "500"))
    max_failure_ratio = float(os.getenv("MAX_FAILURE_RATIO", "0.01"))
    max_p95_ms = int(os.getenv("MAX_P95_MS", "1500"))
    max_read_p95_ms = int(os.getenv("MAX_READ_P95_MS", "1000"))
    violations = []
    if total.num_requests < min_requests:
        violations.append(f"requests {total.num_requests} < {min_requests}")
    if total.fail_ratio > max_failure_ratio:
        violations.append(f"failure ratio {total.fail_ratio:.6f} > {max_failure_ratio}")
    if summary["p95_response_time_ms"] > max_p95_ms:
        violations.append(
            f"aggregate p95 {summary['p95_response_time_ms']} ms > {max_p95_ms} ms"
        )
    if read_p95 > max_read_p95_ms:
        violations.append(f"read p95 {read_p95} ms > {max_read_p95_ms} ms")
    if SERVER_ERRORS:
        violations.append(f"HTTP 5xx responses: {SERVER_ERRORS}")
    if LOCUST_EXCEPTIONS:
        violations.append(f"Locust exceptions: {LOCUST_EXCEPTIONS}")
    if violations:
        environment.process_exit_code = 1
        (RESULTS_DIR / "guardrail-failures.txt").write_text(
            "\n".join(violations) + "\n", encoding="utf-8"
        )


class CatalogUser(HttpUser):
    weight = 7
    host = CORE_URL
    wait_time = between(0.1, 0.5)

    @task
    def browse_catalog(self) -> None:
        self.client.get("/api/v1/products?limit=20", name="[read] GET /products")
        self.client.get(f"/api/v1/products/{PRODUCT_ID}", name="[read] GET /products/{id}")
        self.client.get(
            f"{INVENTORY_URL}/api/v1/inventory/{PRODUCT_ID}",
            name="[read] GET /inventory/{id}",
        )


class CheckoutUser(HttpUser):
    weight = 3
    host = CORE_URL
    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        self.email = f"load-{RUN_ID}-{uuid.uuid4().hex}@example.com"
        password = "LoadCustomer123!"
        with self.client.post(
            "/api/v1/auth/register",
            json={"email": self.email, "password": password},
            name="[write] POST /auth/register",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(f"registration returned {response.status_code}")
                self.token = ""
                return
        with self.client.post(
            "/api/v1/auth/token",
            data={"username": self.email, "password": password},
            name="[write] POST /auth/token",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"login returned {response.status_code}")
                self.token = ""
                return
            self.token = response.json()["access_token"]

    @task
    def checkout_and_cancel(self) -> None:
        if not self.token:
            return
        headers = {"Authorization": f"Bearer {self.token}"}
        reserve_key = f"load-{RUN_ID}-{uuid.uuid4().hex}"
        with self.client.post(
            f"{INVENTORY_URL}/api/v1/reservations",
            json={"product_id": PRODUCT_ID, "quantity": 1},
            headers=headers | {"Idempotency-Key": reserve_key},
            name="[write] POST /reservations",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(f"reserve returned {response.status_code}")
                return
            reservation_id = response.json()["id"]

        order_key = f"load-{RUN_ID}-{uuid.uuid4().hex}"
        with self.client.post(
            f"{ORDERS_URL}/api/v1/orders",
            json={"reservation_id": reservation_id},
            headers=headers | {"Idempotency-Key": order_key},
            name="[write] POST /orders",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(f"order returned {response.status_code}")
                self.client.post(
                    f"{INVENTORY_URL}/api/v1/reservations/{reservation_id}/release",
                    headers=headers,
                    name="[write] POST /reservations/{id}/release",
                )
                return
            order_id = response.json()["id"]

        self.client.get(
            f"{ORDERS_URL}/api/v1/orders/{order_id}",
            headers=headers,
            name="[write] GET /orders/{id}",
        )
        self.client.post(
            f"{ORDERS_URL}/api/v1/orders/{order_id}/cancel",
            headers=headers,
            name="[write] POST /orders/{id}/cancel",
        )
