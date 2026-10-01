from decimal import Decimal
import uuid

import psycopg
import pytest
import requests

from qa.conftest import BASE_URL, DATABASE_URL


@pytest.mark.regression
def test_created_category_matches_postgresql(created_category: dict) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT name, slug FROM categories WHERE id = %s", (created_category["id"],)
        )
        row = cursor.fetchone()

    assert row == (created_category["name"], created_category["slug"])


@pytest.mark.regression
def test_created_product_matches_postgresql(created_product: dict) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT sku, name, price, category_id, is_active FROM products WHERE id = %s",
            (created_product["id"],),
        )
        row = cursor.fetchone()

    assert row == (
        created_product["sku"],
        created_product["name"],
        Decimal(created_product["price"]),
        uuid.UUID(created_product["category_id"]),
        created_product["is_active"],
    )


@pytest.mark.regression
def test_product_update_is_persisted_in_postgresql(created_product: dict) -> None:
    response = requests.patch(
        f"{BASE_URL}/api/v1/products/{created_product['id']}",
        json={"name": "Database Verified Test Product"},
        timeout=5,
    )
    assert response.status_code == 200

    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT name FROM products WHERE id = %s", (created_product["id"],))
        row = cursor.fetchone()

    assert row == ("Database Verified Test Product",)
