import os
import uuid
from collections.abc import Generator

import psycopg
import pytest
import requests
from redis import Redis

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
INVENTORY_URL = os.getenv("INVENTORY_URL", "http://localhost:8001")
ORDERS_URL = os.getenv("ORDERS_URL", "http://localhost:8002")
WEB_URL = os.getenv("WEB_URL", "http://localhost:8080")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://commerce:commerce@localhost:5432/commerce"
)
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
JWT_SECRET = os.getenv("JWT_SECRET", "local-demo-secret-not-for-production")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "LocalAdmin123!")


def cleanup_test_data() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM orders WHERE product_id IN "
                "(SELECT id FROM products WHERE sku LIKE 'TEST-%')"
            )
            cursor.execute(
                "DELETE FROM reservations WHERE product_id IN "
                "(SELECT id FROM products WHERE sku LIKE 'TEST-%')"
            )
            cursor.execute(
                "DELETE FROM inventory_stock WHERE product_id IN "
                "(SELECT id FROM products WHERE sku LIKE 'TEST-%')"
            )
            cursor.execute("DELETE FROM products WHERE sku LIKE 'TEST-%'")
            cursor.execute("DELETE FROM categories WHERE slug LIKE 'test-%'")
            cursor.execute("DELETE FROM users WHERE email LIKE 'test-%@example.com'")
    client = Redis.from_url(REDIS_URL, decode_responses=True)
    for key in client.scan_iter("inventory:idem:*"):
        client.delete(key)


@pytest.fixture(autouse=True)
def isolated_test_data() -> Generator[None, None, None]:
    cleanup_test_data()
    yield
    cleanup_test_data()


@pytest.fixture
def category_payload() -> dict[str, str]:
    suffix = uuid.uuid4().hex
    return {"name": f"Test Category {suffix}", "slug": f"test-{suffix}"}


def login_headers(email: str, password: str) -> dict[str, str]:
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/token",
        data={"username": email, "password": password},
        timeout=5,
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return login_headers(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
def customer_credentials() -> dict[str, str]:
    suffix = uuid.uuid4().hex
    return {"email": f"test-{suffix}@example.com", "password": "Customer123!"}


@pytest.fixture
def registered_customer(customer_credentials: dict[str, str]) -> dict:
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register", json=customer_credentials, timeout=5
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def customer_headers(
    registered_customer: dict, customer_credentials: dict[str, str]
) -> dict[str, str]:
    return login_headers(customer_credentials["email"], customer_credentials["password"])


@pytest.fixture
def created_category(category_payload: dict[str, str], admin_headers: dict[str, str]) -> dict:
    response = requests.post(
        f"{BASE_URL}/api/v1/categories", json=category_payload, headers=admin_headers, timeout=5
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def product_payload(created_category: dict) -> dict:
    suffix = uuid.uuid4().hex.upper()
    return {
        "sku": f"TEST-{suffix}",
        "name": f"Test Product {suffix}",
        "description": "Created by an isolated automated test",
        "price": "19.95",
        "category_id": created_category["id"],
        "is_active": True,
    }


@pytest.fixture
def created_product(product_payload: dict, admin_headers: dict[str, str]) -> dict:
    response = requests.post(
        f"{BASE_URL}/api/v1/products", json=product_payload, headers=admin_headers, timeout=5
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def stocked_product(created_product: dict, admin_headers: dict[str, str]) -> dict:
    response = requests.put(
        f"{INVENTORY_URL}/api/v1/inventory/{created_product['id']}",
        json={"quantity": 10},
        headers=admin_headers,
        timeout=5,
    )
    assert response.status_code == 200
    return created_product


@pytest.fixture
def reservation_payload(stocked_product: dict) -> dict:
    return {"product_id": stocked_product["id"], "quantity": 2}


@pytest.fixture
def created_reservation(
    reservation_payload: dict, customer_headers: dict[str, str]
) -> dict:
    response = requests.post(
        f"{INVENTORY_URL}/api/v1/reservations",
        json=reservation_payload,
        headers=customer_headers | {"Idempotency-Key": f"test-{uuid.uuid4().hex}"},
        timeout=5,
    )
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def created_order(created_reservation: dict, customer_headers: dict[str, str]) -> dict:
    response = requests.post(
        f"{ORDERS_URL}/api/v1/orders",
        json={"reservation_id": created_reservation["id"]},
        headers=customer_headers | {"Idempotency-Key": f"test-{uuid.uuid4().hex}"},
        timeout=5,
    )
    assert response.status_code == 201
    return response.json()
