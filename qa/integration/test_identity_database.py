import psycopg
import pytest

from qa.conftest import DATABASE_URL


@pytest.mark.regression
def test_registered_user_is_stored_with_argon2_hash(
    registered_customer: dict, customer_credentials: dict[str, str]
) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT email, password_hash, role, is_active FROM users WHERE id = %s",
            (registered_customer["id"],),
        )
        row = cursor.fetchone()

    assert row is not None
    assert row[0] == customer_credentials["email"]
    assert row[1].startswith("$argon2")
    assert row[1] != customer_credentials["password"]
    assert row[2:] == ("customer", True)
