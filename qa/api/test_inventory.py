import uuid

import pytest
import requests

from qa.conftest import BASE_URL, INVENTORY_URL


@pytest.mark.smoke
def test_inventory_health_check() -> None:
    response = requests.get(f"{INVENTORY_URL}/health", timeout=5)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "inventory-api"}


@pytest.mark.smoke
def test_inventory_readiness_check() -> None:
    response = requests.get(f"{INVENTORY_URL}/ready", timeout=5)

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "postgres": "ok", "redis": "ok"}


@pytest.mark.regression
def test_admin_can_set_and_public_can_read_stock(
    created_product: dict, admin_headers: dict[str, str]
) -> None:
    updated = requests.put(
        f"{INVENTORY_URL}/api/v1/inventory/{created_product['id']}",
        json={"quantity": 7},
        headers=admin_headers,
        timeout=5,
    )
    public = requests.get(
        f"{INVENTORY_URL}/api/v1/inventory/{created_product['id']}", timeout=5
    )

    assert updated.status_code == 200
    assert updated.json()["available_quantity"] == 7
    assert public.status_code == 200
    assert public.json() == updated.json()


@pytest.mark.regression
def test_set_stock_requires_token(created_product: dict) -> None:
    response = requests.put(
        f"{INVENTORY_URL}/api/v1/inventory/{created_product['id']}",
        json={"quantity": 7},
        timeout=5,
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.regression
def test_customer_cannot_set_stock(
    created_product: dict, customer_headers: dict[str, str]
) -> None:
    response = requests.put(
        f"{INVENTORY_URL}/api/v1/inventory/{created_product['id']}",
        json={"quantity": 7},
        headers=customer_headers,
        timeout=5,
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


@pytest.mark.regression
def test_set_stock_rejects_negative_quantity(
    created_product: dict, admin_headers: dict[str, str]
) -> None:
    response = requests.put(
        f"{INVENTORY_URL}/api/v1/inventory/{created_product['id']}",
        json={"quantity": -1},
        headers=admin_headers,
        timeout=5,
    )

    assert response.status_code == 422


@pytest.mark.regression
def test_set_stock_rejects_unknown_product(admin_headers: dict[str, str]) -> None:
    response = requests.put(
        f"{INVENTORY_URL}/api/v1/inventory/{uuid.uuid4()}",
        json={"quantity": 1},
        headers=admin_headers,
        timeout=5,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found"


@pytest.mark.regression
def test_get_unknown_inventory_returns_404() -> None:
    response = requests.get(f"{INVENTORY_URL}/api/v1/inventory/{uuid.uuid4()}", timeout=5)

    assert response.status_code == 404
    assert response.json()["detail"] == "Inventory not found"


@pytest.mark.regression
def test_total_quantity_cannot_be_set_below_reserved(
    stocked_product: dict,
    created_reservation: dict,
    admin_headers: dict[str, str],
) -> None:
    response = requests.put(
        f"{INVENTORY_URL}/api/v1/inventory/{stocked_product['id']}",
        json={"quantity": created_reservation["quantity"] - 1},
        headers=admin_headers,
        timeout=5,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Quantity is below the reserved amount"


@pytest.mark.regression
def test_product_with_inventory_cannot_be_deleted(
    stocked_product: dict, admin_headers: dict[str, str]
) -> None:
    response = requests.delete(
        f"{BASE_URL}/api/v1/products/{stocked_product['id']}",
        headers=admin_headers,
        timeout=5,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Product has inventory or reservation records"
