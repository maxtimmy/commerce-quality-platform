import pytest
import requests

from qa.conftest import BASE_URL


def assert_unauthorized(response: requests.Response) -> None:
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def assert_forbidden(response: requests.Response) -> None:
    assert response.status_code == 403
    assert response.json()["detail"] == "Admin role required"


@pytest.mark.regression
def test_category_create_requires_token(category_payload: dict) -> None:
    assert_unauthorized(requests.post(f"{BASE_URL}/api/v1/categories", json=category_payload, timeout=5))


@pytest.mark.regression
def test_category_create_rejects_customer(category_payload: dict, customer_headers: dict[str, str]) -> None:
    assert_forbidden(
        requests.post(
            f"{BASE_URL}/api/v1/categories", json=category_payload, headers=customer_headers, timeout=5
        )
    )


@pytest.mark.regression
def test_category_update_requires_token(created_category: dict) -> None:
    assert_unauthorized(
        requests.patch(
            f"{BASE_URL}/api/v1/categories/{created_category['id']}", json={"name": "Blocked"}, timeout=5
        )
    )


@pytest.mark.regression
def test_category_update_rejects_customer(created_category: dict, customer_headers: dict[str, str]) -> None:
    assert_forbidden(
        requests.patch(
            f"{BASE_URL}/api/v1/categories/{created_category['id']}",
            json={"name": "Blocked"},
            headers=customer_headers,
            timeout=5,
        )
    )


@pytest.mark.regression
def test_category_delete_requires_token(created_category: dict) -> None:
    assert_unauthorized(requests.delete(f"{BASE_URL}/api/v1/categories/{created_category['id']}", timeout=5))


@pytest.mark.regression
def test_category_delete_rejects_customer(created_category: dict, customer_headers: dict[str, str]) -> None:
    assert_forbidden(
        requests.delete(
            f"{BASE_URL}/api/v1/categories/{created_category['id']}", headers=customer_headers, timeout=5
        )
    )


@pytest.mark.regression
def test_product_create_requires_token(product_payload: dict) -> None:
    assert_unauthorized(requests.post(f"{BASE_URL}/api/v1/products", json=product_payload, timeout=5))


@pytest.mark.regression
def test_product_create_rejects_customer(product_payload: dict, customer_headers: dict[str, str]) -> None:
    assert_forbidden(
        requests.post(
            f"{BASE_URL}/api/v1/products", json=product_payload, headers=customer_headers, timeout=5
        )
    )


@pytest.mark.regression
def test_product_update_requires_token(created_product: dict) -> None:
    assert_unauthorized(
        requests.patch(
            f"{BASE_URL}/api/v1/products/{created_product['id']}", json={"name": "Blocked"}, timeout=5
        )
    )


@pytest.mark.regression
def test_product_update_rejects_customer(created_product: dict, customer_headers: dict[str, str]) -> None:
    assert_forbidden(
        requests.patch(
            f"{BASE_URL}/api/v1/products/{created_product['id']}",
            json={"name": "Blocked"},
            headers=customer_headers,
            timeout=5,
        )
    )


@pytest.mark.regression
def test_product_delete_requires_token(created_product: dict) -> None:
    assert_unauthorized(requests.delete(f"{BASE_URL}/api/v1/products/{created_product['id']}", timeout=5))


@pytest.mark.regression
def test_product_delete_rejects_customer(created_product: dict, customer_headers: dict[str, str]) -> None:
    assert_forbidden(
        requests.delete(
            f"{BASE_URL}/api/v1/products/{created_product['id']}", headers=customer_headers, timeout=5
        )
    )


@pytest.mark.regression
def test_catalog_reads_remain_public(created_category: dict, created_product: dict) -> None:
    assert requests.get(f"{BASE_URL}/api/v1/categories", timeout=5).status_code == 200
    assert requests.get(f"{BASE_URL}/api/v1/categories/{created_category['id']}", timeout=5).status_code == 200
    assert requests.get(f"{BASE_URL}/api/v1/products", timeout=5).status_code == 200
    assert requests.get(f"{BASE_URL}/api/v1/products/{created_product['id']}", timeout=5).status_code == 200


@pytest.mark.smoke
def test_system_endpoints_remain_public() -> None:
    assert requests.get(f"{BASE_URL}/health", timeout=5).status_code == 200
    assert requests.get(f"{BASE_URL}/ready", timeout=5).status_code == 200
