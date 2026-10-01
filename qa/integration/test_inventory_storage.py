import uuid

import psycopg
import pytest
import requests
from redis import Redis

from qa.conftest import DATABASE_URL, INVENTORY_URL, REDIS_URL


@pytest.mark.regression
def test_stock_update_matches_postgresql(
    stocked_product: dict, admin_headers: dict[str, str]
) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT available_quantity, reserved_quantity, version "
            "FROM inventory_stock WHERE product_id = %s",
            (stocked_product["id"],),
        )
        row = cursor.fetchone()

    assert row == (10, 0, 1)


@pytest.mark.regression
def test_reservation_updates_postgresql_atomically(created_reservation: dict) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT available_quantity, reserved_quantity FROM inventory_stock WHERE product_id = %s",
            (created_reservation["product_id"],),
        )
        stock = cursor.fetchone()
        cursor.execute(
            "SELECT quantity, status, user_id FROM reservations WHERE id = %s",
            (created_reservation["id"],),
        )
        reservation = cursor.fetchone()

    assert stock == (8, 2)
    assert reservation == (
        created_reservation["quantity"],
        "active",
        uuid.UUID(created_reservation["user_id"]),
    )


@pytest.mark.regression
def test_idempotency_mapping_is_cached_in_redis(
    reservation_payload: dict, customer_headers: dict[str, str]
) -> None:
    key = f"test-{uuid.uuid4().hex}"
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations",
        json=reservation_payload,
        headers=customer_headers | {"Idempotency-Key": key},
        timeout=5,
    )
    assert response.status_code == 201

    client = Redis.from_url(REDIS_URL, decode_responses=True)
    redis_key = f"inventory:idem:{response.json()['user_id']}:{key}"

    assert client.get(redis_key) == response.json()["id"]
    assert 1 <= client.ttl(redis_key) <= 600


@pytest.mark.regression
def test_release_restores_postgresql_quantities_once(
    created_reservation: dict, customer_headers: dict[str, str]
) -> None:
    url = f"{INVENTORY_URL}/api/v1/reservations/{created_reservation['id']}/release"
    assert requests.post(url, headers=customer_headers, timeout=5).status_code == 200
    assert requests.post(url, headers=customer_headers, timeout=5).status_code == 200

    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT available_quantity, reserved_quantity FROM inventory_stock WHERE product_id = %s",
            (created_reservation["product_id"],),
        )
        stock = cursor.fetchone()
        cursor.execute(
            "SELECT status, released_at IS NOT NULL FROM reservations WHERE id = %s",
            (created_reservation["id"],),
        )
        reservation = cursor.fetchone()

    assert stock == (10, 0)
    assert reservation == ("released", True)
