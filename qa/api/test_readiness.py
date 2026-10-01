import pytest
import requests

from qa.conftest import BASE_URL


@pytest.mark.smoke
def test_readiness_reports_available_dependencies() -> None:
    response = requests.get(f"{BASE_URL}/ready", timeout=5)

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "postgres": "ok", "redis": "ok"}
