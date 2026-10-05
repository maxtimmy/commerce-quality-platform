import os
import sys
import uuid

import psycopg
from redis import Redis

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://commerce:commerce@postgres:5432/commerce")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


def cleanup() -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "DELETE FROM orders WHERE user_id IN "
            "(SELECT id FROM users WHERE email LIKE 'load-%@example.com') "
            "OR product_id IN (SELECT id FROM products WHERE sku LIKE 'LOAD-%')"
        )
        cursor.execute(
            "DELETE FROM reservations WHERE user_id IN "
            "(SELECT id FROM users WHERE email LIKE 'load-%@example.com') "
            "OR product_id IN (SELECT id FROM products WHERE sku LIKE 'LOAD-%')"
        )
        cursor.execute(
            "DELETE FROM inventory_stock WHERE product_id IN "
            "(SELECT id FROM products WHERE sku LIKE 'LOAD-%')"
        )
        cursor.execute("DELETE FROM products WHERE sku LIKE 'LOAD-%'")
        cursor.execute("DELETE FROM categories WHERE slug LIKE 'load-%'")
        cursor.execute("DELETE FROM users WHERE email LIKE 'load-%@example.com'")

    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    for key in redis.scan_iter("inventory:idem:*:load-*"):
        redis.delete(key)


def setup(run_id: str) -> str:
    cleanup()
    category_id = uuid.uuid4()
    product_id = uuid.uuid4()
    slug = f"load-{run_id.lower()}"
    sku = f"LOAD-{run_id.upper()}"
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO categories (id, name, slug) VALUES (%s, %s, %s)",
            (category_id, f"Load Category {run_id}", slug),
        )
        cursor.execute(
            "INSERT INTO products "
            "(id, sku, name, description, price, category_id, is_active) "
            "VALUES (%s, %s, %s, %s, %s, %s, true)",
            (product_id, sku, f"Load Product {run_id}", "Dedicated Locust data", "49.90", category_id),
        )
        cursor.execute(
            "INSERT INTO inventory_stock "
            "(product_id, available_quantity, reserved_quantity, version) "
            "VALUES (%s, 100000, 0, 1)",
            (product_id,),
        )
    return str(product_id)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "cleanup":
        raise SystemExit("Usage: data.py cleanup")
    cleanup()
    print("Load-test data cleanup completed")
