import uuid
from datetime import datetime, timedelta, timezone

import jwt
import psycopg
import pytest
import requests

from qa.conftest import BASE_URL, DATABASE_URL, JWT_SECRET


@pytest.mark.regression
def test_register_creates_customer_without_sensitive_fields(customer_credentials: dict[str, str]) -> None:
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register", json=customer_credentials, timeout=5
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == customer_credentials["email"]
    assert body["role"] == "customer"
    assert body["is_active"] is True
    assert "password" not in body
    assert "password_hash" not in body


@pytest.mark.regression
def test_register_normalizes_email_to_lowercase(customer_credentials: dict[str, str]) -> None:
    customer_credentials["email"] = customer_credentials["email"].upper()

    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register", json=customer_credentials, timeout=5
    )

    assert response.status_code == 201
    assert response.json()["email"] == customer_credentials["email"].lower()


@pytest.mark.regression
def test_register_rejects_duplicate_email_case_insensitively(
    registered_customer: dict, customer_credentials: dict[str, str]
) -> None:
    duplicate = customer_credentials | {"email": customer_credentials["email"].upper()}

    response = requests.post(f"{BASE_URL}/api/v1/auth/register", json=duplicate, timeout=5)

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


@pytest.mark.regression
def test_register_rejects_invalid_email() -> None:
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register",
        json={"email": "not-an-email", "password": "Customer123!"},
        timeout=5,
    )

    assert response.status_code == 422


@pytest.mark.regression
def test_register_rejects_short_password(customer_credentials: dict[str, str]) -> None:
    customer_credentials["password"] = "short"

    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register", json=customer_credentials, timeout=5
    )

    assert response.status_code == 422


@pytest.mark.regression
def test_register_rejects_password_over_128_bytes(customer_credentials: dict[str, str]) -> None:
    customer_credentials["password"] = "я" * 65

    response = requests.post(
        f"{BASE_URL}/api/v1/auth/register", json=customer_credentials, timeout=5
    )

    assert response.status_code == 422


@pytest.mark.regression
def test_register_rejects_client_supplied_role(customer_credentials: dict[str, str]) -> None:
    payload = customer_credentials | {"role": "admin"}

    response = requests.post(f"{BASE_URL}/api/v1/auth/register", json=payload, timeout=5)

    assert response.status_code == 422


@pytest.mark.regression
def test_login_returns_short_lived_bearer_token(
    registered_customer: dict, customer_credentials: dict[str, str]
) -> None:
    before = datetime.now(timezone.utc).timestamp()
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/token",
        data={"username": customer_credentials["email"], "password": customer_credentials["password"]},
        timeout=5,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 900
    claims = jwt.decode(body["access_token"], JWT_SECRET, algorithms=["HS256"])
    assert claims["sub"] == registered_customer["id"]
    assert claims["role"] == "customer"
    assert 899 <= claims["exp"] - max(claims["iat"], before) <= 900


@pytest.mark.regression
def test_login_rejects_wrong_password_with_generic_error(
    registered_customer: dict, customer_credentials: dict[str, str]
) -> None:
    response = requests.post(
        f"{BASE_URL}/api/v1/auth/token",
        data={"username": customer_credentials["email"], "password": "WrongPassword!"},
        timeout=5,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.regression
def test_login_unknown_email_uses_same_generic_error() -> None:
    for username in (f"test-{uuid.uuid4().hex}@example.com", "invalid\x00email@example.com"):
        response = requests.post(
            f"{BASE_URL}/api/v1/auth/token",
            data={"username": username, "password": "WrongPassword!"},
            timeout=5,
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid email or password"


@pytest.mark.regression
def test_me_returns_authenticated_user(
    registered_customer: dict, customer_headers: dict[str, str]
) -> None:
    response = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=customer_headers, timeout=5)

    assert response.status_code == 200
    assert response.json() == registered_customer


@pytest.mark.regression
def test_me_rejects_missing_token() -> None:
    response = requests.get(f"{BASE_URL}/api/v1/auth/me", timeout=5)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.regression
def test_me_rejects_malformed_token() -> None:
    response = requests.get(
        f"{BASE_URL}/api/v1/auth/me", headers={"Authorization": "Bearer not-a-jwt"}, timeout=5
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.regression
def test_me_rejects_token_with_changed_signature(customer_headers: dict[str, str]) -> None:
    token = customer_headers["Authorization"].split()[1]
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    changed_token = f"{header}.{payload}.{replacement}{signature[1:]}"

    response = requests.get(
        f"{BASE_URL}/api/v1/auth/me",
        headers={"Authorization": f"Bearer {changed_token}"},
        timeout=5,
    )

    assert response.status_code == 401


@pytest.mark.regression
def test_me_rejects_expired_token(registered_customer: dict) -> None:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": registered_customer["id"],
            "role": "customer",
            "iat": now - timedelta(minutes=20),
            "exp": now - timedelta(minutes=5),
        },
        JWT_SECRET,
        algorithm="HS256",
    )

    response = requests.get(
        f"{BASE_URL}/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=5
    )

    assert response.status_code == 401


@pytest.mark.regression
def test_me_rejects_token_for_unknown_user() -> None:
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "role": "customer",
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        JWT_SECRET,
        algorithm="HS256",
    )

    response = requests.get(
        f"{BASE_URL}/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=5
    )

    assert response.status_code == 401


@pytest.mark.regression
def test_me_rejects_inactive_user(
    registered_customer: dict, customer_headers: dict[str, str]
) -> None:
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute("UPDATE users SET is_active = false WHERE id = %s", (registered_customer["id"],))

    response = requests.get(f"{BASE_URL}/api/v1/auth/me", headers=customer_headers, timeout=5)

    assert response.status_code == 401


@pytest.mark.regression
def test_me_rejects_non_bearer_authorization(customer_headers: dict[str, str]) -> None:
    token = customer_headers["Authorization"].split()[1]

    response = requests.get(
        f"{BASE_URL}/api/v1/auth/me", headers={"Authorization": f"Basic {token}"}, timeout=5
    )

    assert response.status_code == 401
