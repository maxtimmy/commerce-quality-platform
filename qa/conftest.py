import os
import uuid
from collections.abc import Generator

import psycopg
import pytest
import requests

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://commerce:commerce@localhost:5432/commerce"
)


def cleanup_test_data() -> None:
    with psycopg.connect(DATABASE_URL) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM products WHERE sku LIKE 'TEST-%'")
            cursor.execute("DELETE FROM categories WHERE slug LIKE 'test-%'")


@pytest.fixture(autouse=True)
def isolated_test_data() -> Generator[None, None, None]:
    cleanup_test_data()
    yield
    cleanup_test_data()


@pytest.fixture
def category_payload() -> dict[str, str]:
    suffix = uuid.uuid4().hex
    return {"name": f"Test Category {suffix}", "slug": f"test-{suffix}"}


@pytest.fixture
def created_category(category_payload: dict[str, str]) -> dict:
    response = requests.post(f"{BASE_URL}/api/v1/categories", json=category_payload, timeout=5)
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
def created_product(product_payload: dict) -> dict:
    response = requests.post(f"{BASE_URL}/api/v1/products", json=product_payload, timeout=5)
    assert response.status_code == 201
    return response.json()
