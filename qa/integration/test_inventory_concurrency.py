import uuid
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest
import requests

from qa.conftest import DATABASE_URL, INVENTORY_URL


@pytest.mark.regression
def test_concurrent_reservations_never_oversell(
    stocked_product: dict,
    admin_headers: dict[str, str],
    customer_headers: dict[str, str],
) -> None:
    set_response = requests.put(
        f"{INVENTORY_URL}/api/v1/inventory/{stocked_product['id']}",
        json={"quantity": 5},
        headers=admin_headers,
        timeout=5,
    )
    assert set_response.status_code == 200

    def reserve_once(_: int) -> requests.Response:
        return requests.post(
            f"{INVENTORY_URL}/api/v1/reservations",
            json={"product_id": stocked_product["id"], "quantity": 1},
            headers=customer_headers | {"Idempotency-Key": f"test-{uuid.uuid4().hex}"},
            timeout=10,
        )

    with ThreadPoolExecutor(max_workers=20) as executor:
        responses = list(executor.map(reserve_once, range(20)))

    assert sum(response.status_code == 201 for response in responses) == 5
    assert sum(response.status_code == 409 for response in responses) == 15
    assert all(
        response.status_code == 201 or response.json()["detail"] == "Insufficient inventory"
        for response in responses
    )

    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT available_quantity, reserved_quantity FROM inventory_stock WHERE product_id = %s",
            (stocked_product["id"],),
        )
        stock = cursor.fetchone()
        cursor.execute(
            "SELECT count(*), sum(quantity) FROM reservations WHERE product_id = %s AND status = 'active'",
            (stocked_product["id"],),
        )
        reservations = cursor.fetchone()

    assert stock == (0, 5)
    assert reservations == (5, 5)


@pytest.mark.regression
def test_concurrent_idempotent_replays_create_one_reservation(
    reservation_payload: dict, customer_headers: dict[str, str]
) -> None:
    idempotency_key = f"test-{uuid.uuid4().hex}"

    def replay(_: int) -> requests.Response:
        return requests.post(
            f"{INVENTORY_URL}/api/v1/reservations",
            json=reservation_payload,
            headers=customer_headers | {"Idempotency-Key": idempotency_key},
            timeout=10,
        )

    with ThreadPoolExecutor(max_workers=10) as executor:
        responses = list(executor.map(replay, range(10)))

    assert sum(response.status_code == 201 for response in responses) == 1
    assert sum(response.status_code == 200 for response in responses) == 9
    reservation_ids = {response.json()["id"] for response in responses}
    assert len(reservation_ids) == 1

    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT available_quantity, reserved_quantity FROM inventory_stock WHERE product_id = %s",
            (reservation_payload["product_id"],),
        )
        stock = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM reservations WHERE user_id = %s AND idempotency_key = %s",
            (responses[0].json()["user_id"], idempotency_key),
        )
        count = cursor.fetchone()[0]

    assert stock == (8, 2)
    assert count == 1
