import uuid

import psycopg
import pytest
import requests
from playwright.sync_api import Page, expect

from qa.conftest import DATABASE_URL, INVENTORY_URL, WEB_URL


def open_store(page: Page) -> None:
    page.goto(WEB_URL)
    expect(page.get_by_test_id("catalog-status")).to_be_hidden(timeout=10_000)


def login(page: Page, credentials: dict[str, str]) -> None:
    page.get_by_test_id("email").fill(credentials["email"])
    page.get_by_test_id("password").fill(credentials["password"])
    page.get_by_test_id("login-submit").click()
    expect(page.get_by_test_id("user-email")).to_have_text(credentials["email"], timeout=10_000)


def product_card(page: Page, product_id: str):
    return page.locator(f'[data-testid="product-card"][data-product-id="{product_id}"]')


@pytest.mark.ui
def test_web_health_and_page_load(ui_page: Page) -> None:
    response = requests.get(f"{WEB_URL}/health", timeout=5)
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "web"}

    open_store(ui_page)
    expect(ui_page.get_by_role("heading", name="Покупка, которую можно проверить")).to_be_visible()


@pytest.mark.ui
def test_public_catalog_is_visible_without_login(ui_page: Page, stocked_product: dict) -> None:
    open_store(ui_page)

    card = product_card(ui_page, stocked_product["id"])
    expect(card).to_be_visible()
    expect(card).to_contain_text(stocked_product["name"])
    expect(card.get_by_test_id("stock")).to_have_text("В наличии: 10")
    expect(ui_page.get_by_test_id("login-form")).to_be_visible()


@pytest.mark.ui
def test_customer_can_login_and_logout(
    ui_page: Page, registered_customer: dict, customer_credentials: dict[str, str]
) -> None:
    open_store(ui_page)
    login(ui_page, customer_credentials)

    expect(ui_page.get_by_test_id("login-form")).to_be_hidden()
    assert ui_page.evaluate("sessionStorage.getItem('access_token')")
    ui_page.get_by_test_id("logout").click()

    expect(ui_page.get_by_test_id("login-form")).to_be_visible()
    expect(ui_page.get_by_test_id("user-email")).to_be_hidden()
    assert ui_page.evaluate("sessionStorage.getItem('access_token')") is None


@pytest.mark.ui
def test_invalid_login_shows_safe_error(ui_page: Page) -> None:
    open_store(ui_page)
    ui_page.get_by_test_id("email").fill(f"test-{uuid.uuid4().hex}@example.com")
    ui_page.get_by_test_id("password").fill("WrongPassword123!")
    ui_page.get_by_test_id("login-submit").click()

    expect(ui_page.get_by_test_id("login-error")).to_have_text("Неверный email или пароль.")
    assert ui_page.evaluate("sessionStorage.getItem('access_token')") is None


@pytest.mark.ui
def test_checkout_requires_login(ui_page: Page, stocked_product: dict) -> None:
    open_store(ui_page)
    product_card(ui_page, stocked_product["id"]).get_by_test_id("buy").click()

    expect(ui_page.get_by_test_id("login-error")).to_have_text("Войдите, чтобы оформить заказ.")


@pytest.mark.ui
def test_customer_completes_reserve_and_order_flow(
    ui_page: Page,
    stocked_product: dict,
    registered_customer: dict,
    customer_credentials: dict[str, str],
) -> None:
    open_store(ui_page)
    login(ui_page, customer_credentials)
    card = product_card(ui_page, stocked_product["id"])
    card.get_by_test_id("quantity").fill("2")
    card.get_by_test_id("buy").click()

    expect(ui_page.get_by_test_id("order-feedback")).to_contain_text("успешно создан", timeout=10_000)
    expect(ui_page.get_by_test_id("order-card")).to_have_count(1)
    expect(product_card(ui_page, stocked_product["id"]).get_by_test_id("stock")).to_have_text("В наличии: 8")


@pytest.mark.ui
def test_stale_stock_conflict_is_shown_without_order(
    ui_page: Page,
    stocked_product: dict,
    registered_customer: dict,
    customer_credentials: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    open_store(ui_page)
    login(ui_page, customer_credentials)
    assert requests.put(
        f"{INVENTORY_URL}/api/v1/inventory/{stocked_product['id']}",
        json={"quantity": 0},
        headers=admin_headers,
        timeout=5,
    ).status_code == 200

    product_card(ui_page, stocked_product["id"]).get_by_test_id("buy").click()

    expect(ui_page.get_by_test_id("order-feedback")).to_have_text(
        "Недостаточно товара для выбранного количества."
    )
    expect(ui_page.get_by_test_id("order-card")).to_have_count(0)


@pytest.mark.ui
def test_order_failure_releases_reservation(
    ui_page: Page,
    stocked_product: dict,
    registered_customer: dict,
    customer_credentials: dict[str, str],
) -> None:
    open_store(ui_page)
    login(ui_page, customer_credentials)
    ui_page.route(
        "**/gateway/orders/orders",
        lambda route: route.fulfill(status=503, content_type="application/json", body='{"detail":"Injected failure"}'),
    )

    product_card(ui_page, stocked_product["id"]).get_by_test_id("buy").click()
    expect(ui_page.get_by_test_id("order-feedback")).to_contain_text("Не удалось оформить заказ")

    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT available_quantity, reserved_quantity FROM inventory_stock WHERE product_id = %s",
            (stocked_product["id"],),
        )
        stock = cursor.fetchone()
        cursor.execute(
            "SELECT status FROM reservations WHERE product_id = %s",
            (stocked_product["id"],),
        )
        statuses = [row[0] for row in cursor.fetchall()]

    assert stock == (10, 0)
    assert statuses == ["released"]


@pytest.mark.ui
def test_repeated_click_creates_only_one_order(
    ui_page: Page,
    stocked_product: dict,
    registered_customer: dict,
    customer_credentials: dict[str, str],
) -> None:
    open_store(ui_page)
    login(ui_page, customer_credentials)
    button = product_card(ui_page, stocked_product["id"]).get_by_test_id("buy")
    button.evaluate("element => { element.click(); element.click(); }")

    expect(ui_page.get_by_test_id("order-feedback")).to_contain_text("успешно создан", timeout=10_000)
    with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM orders WHERE product_id = %s", (stocked_product["id"],))
        assert cursor.fetchone()[0] == 1


@pytest.mark.ui
def test_mobile_layout_and_keyboard_login(
    ui_page: Page, registered_customer: dict, customer_credentials: dict[str, str]
) -> None:
    ui_page.set_viewport_size({"width": 390, "height": 844})
    open_store(ui_page)
    ui_page.get_by_test_id("email").focus()
    ui_page.keyboard.type(customer_credentials["email"])
    ui_page.keyboard.press("Tab")
    ui_page.keyboard.type(customer_credentials["password"])
    ui_page.keyboard.press("Tab")
    ui_page.keyboard.press("Enter")

    expect(ui_page.get_by_test_id("user-email")).to_have_text(customer_credentials["email"])
    expect(ui_page.get_by_test_id("catalog-grid")).to_be_visible()
