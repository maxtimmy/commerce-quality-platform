from collections.abc import Generator

import pytest
from playwright.sync_api import Page

from qa.conftest import WEB_URL


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args: dict) -> dict:
    args = list(browser_type_launch_args.get("args", []))
    args.append(f"--unsafely-treat-insecure-origin-as-secure={WEB_URL}")
    return browser_type_launch_args | {"args": args}


@pytest.fixture
def ui_page(page: Page) -> Generator[Page, None, None]:
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
    page.on(
        "console",
        lambda message: errors.append(f"console: {message.text}")
        if message.type == "error" and not message.text.startswith("Failed to load resource:")
        else None,
    )
    yield page
    assert errors == []
