import uuid

import pytest
import requests

from qa.conftest import BASE_URL


@pytest.mark.regression
def test_create_category_returns_persisted_representation(category_payload: dict) -> None:
    response = requests.post(f"{BASE_URL}/api/v1/categories", json=category_payload, timeout=5)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == category_payload["name"]
    assert body["slug"] == category_payload["slug"]
    assert body["id"]
    assert body["created_at"]


@pytest.mark.regression
def test_get_category_by_id(created_category: dict) -> None:
    response = requests.get(
        f"{BASE_URL}/api/v1/categories/{created_category['id']}", timeout=5
    )

    assert response.status_code == 200
    assert response.json() == created_category


@pytest.mark.regression
def test_list_categories_is_sorted_by_slug(created_category: dict, category_payload: dict) -> None:
    second = {
        "name": f"Another {category_payload['name']}",
        "slug": f"test-0-{uuid.uuid4().hex}",
    }
    assert requests.post(f"{BASE_URL}/api/v1/categories", json=second, timeout=5).status_code == 201

    response = requests.get(f"{BASE_URL}/api/v1/categories", timeout=5)

    assert response.status_code == 200
    slugs = [item["slug"] for item in response.json()]
    assert slugs == sorted(slugs)


@pytest.mark.regression
def test_update_category_changes_only_sent_field(created_category: dict) -> None:
    response = requests.patch(
        f"{BASE_URL}/api/v1/categories/{created_category['id']}",
        json={"name": "Updated Test Category"},
        timeout=5,
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Test Category"
    assert response.json()["slug"] == created_category["slug"]


@pytest.mark.regression
def test_delete_empty_category(created_category: dict) -> None:
    response = requests.delete(
        f"{BASE_URL}/api/v1/categories/{created_category['id']}", timeout=5
    )

    assert response.status_code == 204
    assert requests.get(
        f"{BASE_URL}/api/v1/categories/{created_category['id']}", timeout=5
    ).status_code == 404


@pytest.mark.regression
def test_create_category_rejects_duplicate_slug(created_category: dict) -> None:
    response = requests.post(
        f"{BASE_URL}/api/v1/categories",
        json={"name": "Different Test Name", "slug": created_category["slug"]},
        timeout=5,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Category name or slug already exists"


@pytest.mark.regression
def test_create_category_rejects_invalid_slug() -> None:
    response = requests.post(
        f"{BASE_URL}/api/v1/categories",
        json={"name": "Invalid Test Category", "slug": "Invalid Slug!"},
        timeout=5,
    )

    assert response.status_code == 422


@pytest.mark.regression
def test_get_unknown_category_returns_404() -> None:
    response = requests.get(f"{BASE_URL}/api/v1/categories/{uuid.uuid4()}", timeout=5)

    assert response.status_code == 404
    assert response.json()["detail"] == "Category not found"


@pytest.mark.regression
def test_category_path_rejects_malformed_uuid() -> None:
    response = requests.get(f"{BASE_URL}/api/v1/categories/not-a-uuid", timeout=5)

    assert response.status_code == 422


@pytest.mark.regression
def test_delete_category_used_by_product(created_category: dict, created_product: dict) -> None:
    response = requests.delete(
        f"{BASE_URL}/api/v1/categories/{created_category['id']}", timeout=5
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Category is used by products"


@pytest.mark.regression
def test_update_category_rejects_null_name(created_category: dict) -> None:
    response = requests.patch(
        f"{BASE_URL}/api/v1/categories/{created_category['id']}", json={"name": None}, timeout=5
    )

    assert response.status_code == 422
