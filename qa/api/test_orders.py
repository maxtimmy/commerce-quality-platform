import uuid

import pytest
import requests

from qa.conftest import BASE_URL, INVENTORY_URL, ORDERS_URL, login_headers


def create_order(reservation_id: str, headers: dict[str, str], key: str | None = None) -> requests.Response:
    request_headers = headers | {"Idempotency-Key": key or f"test-{uuid.uuid4().hex}"}
    return requests.post(
        f"{ORDERS_URL}/api/v1/orders",
        json={"reservation_id": reservation_id},
        headers=request_headers,
        timeout=5,
    )


@pytest.mark.smoke
def test_orders_health() -> None:
    response = requests.get(f"{ORDERS_URL}/health", timeout=5)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "orders-api"}


@pytest.mark.smoke
def test_orders_readiness() -> None:
    response = requests.get(f"{ORDERS_URL}/ready", timeout=5)

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "postgres": "ok"}


@pytest.mark.regression
def test_customer_creates_order_from_own_active_reservation(
    created_reservation: dict, customer_headers: dict[str, str]
) -> None:
    response = create_order(created_reservation["id"], customer_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["reservation_id"] == created_reservation["id"]
    assert body["quantity"] == created_reservation["quantity"]
    assert body["unit_price"] == "19.95"
    assert body["total_amount"] == "39.90"
    assert body["status"] == "created"


@pytest.mark.regression
def test_order_requires_authentication(created_reservation: dict) -> None:
    response = create_order(created_reservation["id"], {})

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.regression
def test_order_rejects_token_with_changed_signature(
    created_reservation: dict, customer_headers: dict[str, str]
) -> None:
    token = customer_headers["Authorization"].split()[1]
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    response = create_order(
        created_reservation["id"],
        {"Authorization": f"Bearer {header}.{payload}.{replacement}{signature[1:]}"},
    )

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.regression
def test_order_requires_idempotency_key(
    created_reservation: dict, customer_headers: dict[str, str]
) -> None:
    response = requests.post(
        f"{ORDERS_URL}/api/v1/orders",
        json={"reservation_id": created_reservation["id"]},
        headers=customer_headers,
        timeout=5,
    )

    assert response.status_code == 422


@pytest.mark.regression
def test_order_rejects_extra_fields(
    created_reservation: dict, customer_headers: dict[str, str]
) -> None:
    response = requests.post(
        f"{ORDERS_URL}/api/v1/orders",
        json={"reservation_id": created_reservation["id"], "unexpected": True},
        headers=customer_headers | {"Idempotency-Key": f"test-{uuid.uuid4().hex}"},
        timeout=5,
    )

    assert response.status_code == 422


@pytest.mark.regression
def test_order_rejects_unknown_reservation(customer_headers: dict[str, str]) -> None:
    response = create_order(str(uuid.uuid4()), customer_headers)

    assert response.status_code == 404
    assert response.json()["detail"] == "Reservation not found"


@pytest.mark.regression
def test_order_rejects_released_reservation(
    created_reservation: dict, customer_headers: dict[str, str]
) -> None:
    release = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations/{created_reservation['id']}/release",
        headers=customer_headers,
        timeout=5,
    )
    assert release.status_code == 200

    response = create_order(created_reservation["id"], customer_headers)

    assert response.status_code == 409
    assert response.json()["detail"] == "Reservation is not active"


@pytest.mark.regression
def test_other_customer_cannot_create_order(created_reservation: dict) -> None:
    email = f"test-{uuid.uuid4().hex}@example.com"
    password = "Customer123!"
    assert requests.post(
        f"{BASE_URL}/api/v1/auth/register", json={"email": email, "password": password}, timeout=5
    ).status_code == 201

    response = create_order(created_reservation["id"], login_headers(email, password))

    assert response.status_code == 403


@pytest.mark.regression
def test_same_order_request_is_idempotent(
    created_reservation: dict, customer_headers: dict[str, str]
) -> None:
    key = f"test-{uuid.uuid4().hex}"
    first = create_order(created_reservation["id"], customer_headers, key)
    replay = create_order(created_reservation["id"], customer_headers, key)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]


@pytest.mark.regression
def test_same_order_key_with_different_payload_conflicts(
    created_reservation: dict, customer_headers: dict[str, str]
) -> None:
    key = f"test-{uuid.uuid4().hex}"
    assert create_order(created_reservation["id"], customer_headers, key).status_code == 201

    response = create_order(str(uuid.uuid4()), customer_headers, key)

    assert response.status_code == 409


@pytest.mark.regression
def test_customer_lists_only_own_orders(
    created_order: dict, customer_headers: dict[str, str]
) -> None:
    response = requests.get(f"{ORDERS_URL}/api/v1/orders", headers=customer_headers, timeout=5)

    assert response.status_code == 200
    assert [order["id"] for order in response.json()] == [created_order["id"]]


@pytest.mark.regression
def test_admin_lists_customer_orders(created_order: dict, admin_headers: dict[str, str]) -> None:
    response = requests.get(f"{ORDERS_URL}/api/v1/orders", headers=admin_headers, timeout=5)

    assert response.status_code == 200
    assert created_order["id"] in {order["id"] for order in response.json()}


@pytest.mark.regression
def test_owner_gets_order(created_order: dict, customer_headers: dict[str, str]) -> None:
    response = requests.get(
        f"{ORDERS_URL}/api/v1/orders/{created_order['id']}", headers=customer_headers, timeout=5
    )

    assert response.status_code == 200
    assert response.json()["id"] == created_order["id"]


@pytest.mark.regression
def test_admin_can_get_customer_order(created_order: dict, admin_headers: dict[str, str]) -> None:
    response = requests.get(
        f"{ORDERS_URL}/api/v1/orders/{created_order['id']}", headers=admin_headers, timeout=5
    )

    assert response.status_code == 200


@pytest.mark.regression
def test_other_customer_cannot_get_order(created_order: dict) -> None:
    email = f"test-{uuid.uuid4().hex}@example.com"
    password = "Customer123!"
    requests.post(
        f"{BASE_URL}/api/v1/auth/register", json={"email": email, "password": password}, timeout=5
    )
    response = requests.get(
        f"{ORDERS_URL}/api/v1/orders/{created_order['id']}",
        headers=login_headers(email, password),
        timeout=5,
    )

    assert response.status_code == 403


@pytest.mark.regression
def test_owner_cancels_order(created_order: dict, customer_headers: dict[str, str]) -> None:
    response = requests.post(
        f"{ORDERS_URL}/api/v1/orders/{created_order['id']}/cancel",
        headers=customer_headers,
        timeout=5,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancelled_at"] is not None


@pytest.mark.regression
def test_admin_can_cancel_customer_order(created_order: dict, admin_headers: dict[str, str]) -> None:
    response = requests.post(
        f"{ORDERS_URL}/api/v1/orders/{created_order['id']}/cancel",
        headers=admin_headers,
        timeout=5,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


@pytest.mark.regression
def test_other_customer_cannot_cancel_order(created_order: dict) -> None:
    email = f"test-{uuid.uuid4().hex}@example.com"
    password = "Customer123!"
    requests.post(
        f"{BASE_URL}/api/v1/auth/register", json={"email": email, "password": password}, timeout=5
    )
    response = requests.post(
        f"{ORDERS_URL}/api/v1/orders/{created_order['id']}/cancel",
        headers=login_headers(email, password),
        timeout=5,
    )

    assert response.status_code == 403


@pytest.mark.regression
def test_repeated_cancel_is_idempotent(
    created_order: dict, customer_headers: dict[str, str]
) -> None:
    url = f"{ORDERS_URL}/api/v1/orders/{created_order['id']}/cancel"
    first = requests.post(url, headers=customer_headers, timeout=5)
    replay = requests.post(url, headers=customer_headers, timeout=5)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert replay.json()["cancelled_at"] == first.json()["cancelled_at"]


@pytest.mark.regression
def test_unknown_order_returns_404(customer_headers: dict[str, str]) -> None:
    response = requests.get(
        f"{ORDERS_URL}/api/v1/orders/{uuid.uuid4()}", headers=customer_headers, timeout=5
    )

    assert response.status_code == 404


@pytest.mark.regression
def test_order_list_rejects_offset_above_postgresql_limit(
    customer_headers: dict[str, str]
) -> None:
    response = requests.get(
        f"{ORDERS_URL}/api/v1/orders",
        params={"offset": 2_147_483_648},
        headers=customer_headers,
        timeout=5,
    )

    assert response.status_code == 422
