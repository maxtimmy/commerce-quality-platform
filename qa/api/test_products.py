import uuid

import pytest
import requests

from qa.conftest import BASE_URL


@pytest.mark.regression
def test_create_product_returns_normalized_price(
    product_payload: dict, admin_headers: dict[str, str]
) -> None:
    response = requests.post(
        f"{BASE_URL}/api/v1/products", json=product_payload, headers=admin_headers, timeout=5
    )

    assert response.status_code == 201
    body = response.json()
    assert body["sku"] == product_payload["sku"]
    assert body["price"] == "19.95"
    assert body["category_id"] == product_payload["category_id"]


@pytest.mark.regression
def test_get_product_by_id(created_product: dict) -> None:
    response = requests.get(f"{BASE_URL}/api/v1/products/{created_product['id']}", timeout=5)

    assert response.status_code == 200
    assert response.json() == created_product


@pytest.mark.regression
def test_update_product_price_preserves_other_fields(
    created_product: dict, admin_headers: dict[str, str]
) -> None:
    response = requests.patch(
        f"{BASE_URL}/api/v1/products/{created_product['id']}",
        json={"price": "25.40"},
        headers=admin_headers,
        timeout=5,
    )

    assert response.status_code == 200
    assert response.json()["price"] == "25.40"
    assert response.json()["sku"] == created_product["sku"]


@pytest.mark.regression
def test_delete_product(created_product: dict, admin_headers: dict[str, str]) -> None:
    response = requests.delete(
        f"{BASE_URL}/api/v1/products/{created_product['id']}", headers=admin_headers, timeout=5
    )

    assert response.status_code == 204
    assert requests.get(
        f"{BASE_URL}/api/v1/products/{created_product['id']}", timeout=5
    ).status_code == 404


@pytest.mark.regression
def test_create_product_rejects_duplicate_sku(
    created_product: dict, product_payload: dict, admin_headers: dict[str, str]
) -> None:
    response = requests.post(
        f"{BASE_URL}/api/v1/products", json=product_payload, headers=admin_headers, timeout=5
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Product SKU already exists"


@pytest.mark.regression
def test_create_product_rejects_unknown_category(
    product_payload: dict, admin_headers: dict[str, str]
) -> None:
    product_payload["category_id"] = str(uuid.uuid4())

    response = requests.post(
        f"{BASE_URL}/api/v1/products", json=product_payload, headers=admin_headers, timeout=5
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Category not found"


@pytest.mark.regression
def test_create_product_rejects_zero_price(
    product_payload: dict, admin_headers: dict[str, str]
) -> None:
    product_payload["price"] = "0.00"

    response = requests.post(
        f"{BASE_URL}/api/v1/products", json=product_payload, headers=admin_headers, timeout=5
    )

    assert response.status_code == 422


@pytest.mark.regression
def test_create_product_rejects_price_with_excess_precision(
    product_payload: dict, admin_headers: dict[str, str]
) -> None:
    product_payload["price"] = "10.999"

    response = requests.post(
        f"{BASE_URL}/api/v1/products", json=product_payload, headers=admin_headers, timeout=5
    )

    assert response.status_code == 422


@pytest.mark.regression
def test_list_products_filters_by_category(created_product: dict) -> None:
    response = requests.get(
        f"{BASE_URL}/api/v1/products",
        params={"category_id": created_product["category_id"]},
        timeout=5,
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [created_product["id"]]


@pytest.mark.regression
def test_list_products_filters_by_active_state(
    created_product: dict, admin_headers: dict[str, str]
) -> None:
    requests.patch(
        f"{BASE_URL}/api/v1/products/{created_product['id']}",
        json={"is_active": False},
        headers=admin_headers,
        timeout=5,
    ).raise_for_status()

    response = requests.get(
        f"{BASE_URL}/api/v1/products", params={"is_active": False}, timeout=5
    )

    assert response.status_code == 200
    assert created_product["id"] in [item["id"] for item in response.json()]


@pytest.mark.regression
def test_list_products_searches_case_insensitively(created_product: dict) -> None:
    response = requests.get(
        f"{BASE_URL}/api/v1/products",
        params={"search": created_product["name"].lower()},
        timeout=5,
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [created_product["id"]]


@pytest.mark.regression
def test_list_products_applies_limit_and_offset(
    created_product: dict, product_payload: dict, admin_headers: dict[str, str]
) -> None:
    second = product_payload | {"sku": f"TEST-Z-{uuid.uuid4().hex.upper()}"}
    assert requests.post(
        f"{BASE_URL}/api/v1/products", json=second, headers=admin_headers, timeout=5
    ).status_code == 201

    response = requests.get(
        f"{BASE_URL}/api/v1/products", params={"search": "TEST-", "limit": 1, "offset": 1}, timeout=5
    )

    assert response.status_code == 200
    assert len(response.json()) == 1


@pytest.mark.regression
def test_list_products_rejects_limit_above_maximum() -> None:
    response = requests.get(f"{BASE_URL}/api/v1/products", params={"limit": 101}, timeout=5)

    assert response.status_code == 422


@pytest.mark.regression
def test_update_product_rejects_unknown_category(
    created_product: dict, admin_headers: dict[str, str]
) -> None:
    response = requests.patch(
        f"{BASE_URL}/api/v1/products/{created_product['id']}",
        json={"category_id": str(uuid.uuid4())},
        headers=admin_headers,
        timeout=5,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Category not found"


@pytest.mark.regression
def test_get_unknown_product_returns_404() -> None:
    response = requests.get(f"{BASE_URL}/api/v1/products/{uuid.uuid4()}", timeout=5)

    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found"


@pytest.mark.regression
def test_update_product_allows_clearing_description(
    created_product: dict, admin_headers: dict[str, str]
) -> None:
    response = requests.patch(
        f"{BASE_URL}/api/v1/products/{created_product['id']}",
        json={"description": None},
        headers=admin_headers,
        timeout=5,
    )

    assert response.status_code == 200
    assert response.json()["description"] is None


@pytest.mark.regression
def test_update_product_rejects_null_price(
    created_product: dict, admin_headers: dict[str, str]
) -> None:
    response = requests.patch(
        f"{BASE_URL}/api/v1/products/{created_product['id']}",
        json={"price": None},
        headers=admin_headers,
        timeout=5,
    )

    assert response.status_code == 422
