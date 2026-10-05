import os

import pytest
import requests


BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")


@pytest.mark.smoke
def test_health_check_reports_running_service() -> None:
    response = requests.get(f"{BASE_URL}/health", timeout=5)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.json() == {"status": "ok", "service": "commerce-api"}
