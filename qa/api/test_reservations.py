import uuid

import pytest
import requests

from qa.conftest import BASE_URL, INVENTORY_URL, login_headers


@pytest.mark.regression
def test_customer_can_reserve_available_inventory(
    reservation_payload: dict, customer_headers: dict[str, str]
) -> None:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations",
        json=reservation_payload,
        headers=customer_headers | {"Idempotency-Key": f"test-{uuid.uuid4().hex}"},
        timeout=5,
    )

    assert response.status_code == 201
    assert response.json()["status"] == "active"
    assert response.json()["quantity"] == reservation_payload["quantity"]


@pytest.mark.regression
def test_reservation_requires_authentication(reservation_payload: dict) -> None:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations",
        json=reservation_payload,
        headers={"Idempotency-Key": f"test-{uuid.uuid4().hex}"},
        timeout=5,
    )

    assert response.status_code == 401


@pytest.mark.regression
def test_reservation_rejects_token_with_changed_signature(
    reservation_payload: dict, customer_headers: dict[str, str]
) -> None:
    token = customer_headers["Authorization"].split()[1]
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    changed_token = f"{header}.{payload}.{replacement}{signature[1:]}"

    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations",
        json=reservation_payload,
        headers={
            "Authorization": f"Bearer {changed_token}",
            "Idempotency-Key": f"test-{uuid.uuid4().hex}",
        },
        timeout=5,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.regression
def test_reservation_requires_idempotency_key(
    reservation_payload: dict, customer_headers: dict[str, str]
) -> None:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations",
        json=reservation_payload,
        headers=customer_headers,
        timeout=5,
    )

    assert response.status_code == 422


@pytest.mark.regression
def test_reservation_rejects_invalid_idempotency_key(
    reservation_payload: dict, customer_headers: dict[str, str]
) -> None:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations",
        json=reservation_payload,
        headers=customer_headers | {"Idempotency-Key": "contains spaces"},
        timeout=5,
    )

    assert response.status_code == 422


@pytest.mark.regression
def test_reservation_rejects_zero_quantity(
    reservation_payload: dict, customer_headers: dict[str, str]
) -> None:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations",
        json=reservation_payload | {"quantity": 0},
        headers=customer_headers | {"Idempotency-Key": f"test-{uuid.uuid4().hex}"},
        timeout=5,
    )

    assert response.status_code == 422


@pytest.mark.regression
def test_reservation_rejects_insufficient_inventory(
    reservation_payload: dict, customer_headers: dict[str, str]
) -> None:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations",
        json=reservation_payload | {"quantity": 11},
        headers=customer_headers | {"Idempotency-Key": f"test-{uuid.uuid4().hex}"},
        timeout=5,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Insufficient inventory"


@pytest.mark.regression
def test_reservation_rejects_unknown_product(customer_headers: dict[str, str]) -> None:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations",
        json={"product_id": str(uuid.uuid4()), "quantity": 1},
        headers=customer_headers | {"Idempotency-Key": f"test-{uuid.uuid4().hex}"},
        timeout=5,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found"


@pytest.mark.regression
def test_same_request_is_replayed_without_second_decrement(
    reservation_payload: dict, customer_headers: dict[str, str]
) -> None:
    headers = customer_headers | {"Idempotency-Key": f"test-{uuid.uuid4().hex}"}
    first = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations", json=reservation_payload, headers=headers, timeout=5
    )
    replay = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations", json=reservation_payload, headers=headers, timeout=5
    )
    stock = requests.get(
        f"{INVENTORY_URL}/api/v1/inventory/{reservation_payload['product_id']}", timeout=5
    )

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert stock.json()["available_quantity"] == 8


@pytest.mark.regression
def test_same_key_with_different_payload_returns_conflict(
    reservation_payload: dict, customer_headers: dict[str, str]
) -> None:
    headers = customer_headers | {"Idempotency-Key": f"test-{uuid.uuid4().hex}"}
    first = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations", json=reservation_payload, headers=headers, timeout=5
    )
    conflict = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations",
        json=reservation_payload | {"quantity": 3},
        headers=headers,
        timeout=5,
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "Idempotency key was used with different payload"


@pytest.mark.regression
def test_owner_can_release_reservation(
    created_reservation: dict, customer_headers: dict[str, str]
) -> None:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations/{created_reservation['id']}/release",
        headers=customer_headers,
        timeout=5,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "released"
    assert response.json()["released_at"] is not None


@pytest.mark.regression
def test_repeated_release_does_not_restore_twice(
    created_reservation: dict, customer_headers: dict[str, str]
) -> None:
    url = f"{INVENTORY_URL}/api/v1/reservations/{created_reservation['id']}/release"
    first = requests.post(url, headers=customer_headers, timeout=5)
    second = requests.post(url, headers=customer_headers, timeout=5)
    stock = requests.get(
        f"{INVENTORY_URL}/api/v1/inventory/{created_reservation['product_id']}", timeout=5
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["released_at"] == first.json()["released_at"]
    assert stock.json()["available_quantity"] == 10


@pytest.mark.regression
def test_other_customer_cannot_release_reservation(created_reservation: dict) -> None:
    email = f"test-{uuid.uuid4().hex}@example.com"
    password = "Customer123!"
    assert requests.post(
        f"{BASE_URL}/api/v1/auth/register", json={"email": email, "password": password}, timeout=5
    ).status_code == 201

    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations/{created_reservation['id']}/release",
        headers=login_headers(email, password),
        timeout=5,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Reservation belongs to another user"


@pytest.mark.regression
def test_admin_can_release_customer_reservation(
    created_reservation: dict, admin_headers: dict[str, str]
) -> None:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations/{created_reservation['id']}/release",
        headers=admin_headers,
        timeout=5,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "released"


@pytest.mark.regression
def test_release_requires_authentication(created_reservation: dict) -> None:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations/{created_reservation['id']}/release", timeout=5
    )

    assert response.status_code == 401


@pytest.mark.regression
def test_release_unknown_reservation_returns_404(customer_headers: dict[str, str]) -> None:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations/{uuid.uuid4()}/release",
        headers=customer_headers,
        timeout=5,
    )

    assert response.status_code == 404
