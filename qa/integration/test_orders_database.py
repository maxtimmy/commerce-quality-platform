from concurrent.futures import ThreadPoolExecutor
import uuid
from decimal import Decimal

import psycopg
import pytest
import requests

from qa.conftest import DATABASE_URL, INVENTORY_URL, ORDERS_URL


@pytest.mark.regression
def test_order_commit_matches_reservation_inventory_and_database(created_order: dict) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT reservation_id, quantity, unit_price, total_amount, status FROM orders WHERE id = %s",
            (created_order["id"],),
        )
        order = cursor.fetchone()
        cursor.execute(
            "SELECT status, committed_at IS NOT NULL FROM reservations WHERE id = %s",
            (created_order["reservation_id"],),
        )
        reservation = cursor.fetchone()
        cursor.execute(
            "SELECT available_quantity, reserved_quantity FROM inventory_stock WHERE product_id = %s",
            (created_order["product_id"],),
        )
        stock = cursor.fetchone()

    assert order == (
        uuid.UUID(created_order["reservation_id"]),
        2,
        Decimal(created_order["unit_price"]),
        Decimal(created_order["total_amount"]),
        "created",
    )
    assert reservation == ("committed", True)
    assert stock == (8, 0)


@pytest.mark.regression
def test_committed_reservation_cannot_be_released(
    created_order: dict, customer_headers: dict[str, str]
) -> None:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations/{created_order['reservation_id']}/release",
        headers=customer_headers,
        timeout=5,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Committed reservation cannot be released"


@pytest.mark.regression
def test_cancel_restores_available_inventory_once(
    created_order: dict, customer_headers: dict[str, str]
) -> None:
    url = f"{ORDERS_URL}/api/v1/orders/{created_order['id']}/cancel"
    assert requests.post(url, headers=customer_headers, timeout=5).status_code == 200
    assert requests.post(url, headers=customer_headers, timeout=5).status_code == 200

    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT available_quantity, reserved_quantity FROM inventory_stock WHERE product_id = %s",
            (created_order["product_id"],),
        )
        stock = cursor.fetchone()
        cursor.execute(
            "SELECT status, cancelled_at IS NOT NULL FROM orders WHERE id = %s",
            (created_order["id"],),
        )
        order = cursor.fetchone()

    assert stock == (10, 0)
    assert order == ("cancelled", True)


@pytest.mark.regression
def test_concurrent_order_commit_creates_exactly_one_order(
    created_reservation: dict, customer_headers: dict[str, str]
) -> None:
    def commit(index: int) -> requests.Response:
        return requests.post(
            f"{ORDERS_URL}/api/v1/orders",
            json={"reservation_id": created_reservation["id"]},
            headers=customer_headers | {"Idempotency-Key": f"test-{index}-{uuid.uuid4().hex}"},
            timeout=10,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(commit, range(2)))

    assert sum(response.status_code == 201 for response in responses) == 1
    assert sum(response.status_code == 409 for response in responses) == 1
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM orders WHERE reservation_id = %s", (created_reservation["id"],))
        count = cursor.fetchone()[0]
        cursor.execute(
            "SELECT available_quantity, reserved_quantity FROM inventory_stock WHERE product_id = %s",
            (created_reservation["product_id"],),
        )
        stock = cursor.fetchone()

    assert count == 1
    assert stock == (8, 0)


@pytest.mark.regression
def test_concurrent_same_key_returns_one_order(
    created_reservation: dict, customer_headers: dict[str, str]
) -> None:
    key = f"test-{uuid.uuid4().hex}"

    def replay(_: int) -> requests.Response:
        return requests.post(
            f"{ORDERS_URL}/api/v1/orders",
            json={"reservation_id": created_reservation["id"]},
            headers=customer_headers | {"Idempotency-Key": key},
            timeout=10,
        )

    with ThreadPoolExecutor(max_workers=10) as executor:
        responses = list(executor.map(replay, range(10)))

    assert sum(response.status_code == 201 for response in responses) == 1
    assert sum(response.status_code == 200 for response in responses) == 9
    assert len({response.json()["id"] for response in responses}) == 1
