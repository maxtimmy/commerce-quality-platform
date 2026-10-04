const endpoints = {
  token: "/gateway/core/auth/token",
  me: "/gateway/core/auth/me",
  products: "/gateway/core/products",
  inventory: "/gateway/inventory/inventory",
  reservations: "/gateway/inventory/reservations",
  orders: "/gateway/orders/orders",
};

const state = { token: sessionStorage.getItem("access_token"), user: null, products: [] };
const elements = {
  loginForm: document.querySelector("#login-form"),
  loginError: document.querySelector("#login-error"),
  userEmail: document.querySelector("#user-email"),
  logout: document.querySelector("#logout-button"),
  catalogGrid: document.querySelector("#catalog-grid"),
  catalogStatus: document.querySelector("#catalog-status"),
  refresh: document.querySelector("#refresh-catalog"),
  ordersSection: document.querySelector("#orders-section"),
  ordersList: document.querySelector("#orders-list"),
  ordersStatus: document.querySelector("#orders-status"),
  orderFeedback: document.querySelector("#order-feedback"),
};

function authHeaders(extra = {}) {
  return state.token ? { ...extra, Authorization: `Bearer ${state.token}` } : extra;
}

function idempotencyKey() {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function api(url, options = {}) {
  const response = await fetch(url, options);
  let body = null;
  if (response.status !== 204) {
    body = await response.json().catch(() => null);
  }
  if (response.status === 401 && state.token) {
    clearSession();
  }
  if (!response.ok) {
    const error = new Error(body?.detail || `Ошибка API: ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return body;
}

function clearSession() {
  state.token = null;
  state.user = null;
  sessionStorage.removeItem("access_token");
  elements.loginForm.hidden = false;
  elements.userEmail.hidden = true;
  elements.logout.hidden = true;
  elements.ordersSection.hidden = true;
}

function showFeedback(message, isError = false) {
  elements.orderFeedback.textContent = message;
  elements.orderFeedback.classList.toggle("error", isError);
  elements.orderFeedback.hidden = false;
}

async function loadSession() {
  if (!state.token) return;
  try {
    state.user = await api(endpoints.me, { headers: authHeaders() });
    elements.userEmail.textContent = state.user.email;
    elements.userEmail.hidden = false;
    elements.logout.hidden = false;
    elements.loginForm.hidden = true;
    elements.ordersSection.hidden = false;
    await loadOrders();
  } catch (_) {
    clearSession();
  }
}

async function loadCatalog() {
  elements.catalogStatus.hidden = false;
  elements.catalogStatus.textContent = "Загружаем каталог…";
  elements.catalogGrid.replaceChildren();
  try {
    const products = await api(endpoints.products);
    state.products = await Promise.all(products.map(async (product) => {
      try {
        const stock = await api(`${endpoints.inventory}/${product.id}`);
        return { ...product, available: stock.available_quantity };
      } catch (error) {
        return { ...product, available: error.status === 404 ? null : 0 };
      }
    }));
    elements.catalogStatus.hidden = state.products.length > 0;
    elements.catalogStatus.textContent = state.products.length ? "" : "В каталоге пока нет товаров.";
    state.products.forEach(renderProduct);
  } catch (error) {
    elements.catalogStatus.textContent = `Не удалось загрузить каталог: ${error.message}`;
  }
}

function renderProduct(product) {
  const card = document.createElement("article");
  card.className = "product-card";
  card.dataset.testid = "product-card";
  card.dataset.productId = product.id;

  const sku = document.createElement("span");
  sku.className = "product-sku";
  sku.textContent = product.sku;
  const title = document.createElement("h3");
  title.textContent = product.name;
  const description = document.createElement("p");
  description.className = "product-description";
  description.textContent = product.description || "Описание пока не добавлено.";

  const meta = document.createElement("div");
  meta.className = "product-meta";
  const price = document.createElement("span");
  price.className = "price";
  price.textContent = `${product.price} ₽`;
  const stock = document.createElement("span");
  stock.className = `stock ${product.available === 0 ? "empty" : ""}`;
  stock.dataset.testid = "stock";
  stock.textContent = product.available === null ? "Нет данных" : product.available > 0 ? `В наличии: ${product.available}` : "Нет в наличии";
  meta.append(price, stock);

  const buyRow = document.createElement("div");
  buyRow.className = "buy-row";
  const quantity = document.createElement("input");
  quantity.type = "number";
  quantity.min = "1";
  quantity.max = String(Math.max(product.available || 1, 1));
  quantity.value = "1";
  quantity.setAttribute("aria-label", `Количество для ${product.name}`);
  quantity.dataset.testid = "quantity";
  const buy = document.createElement("button");
  buy.type = "button";
  buy.className = "button";
  buy.dataset.testid = "buy";
  buy.textContent = "Зарезервировать и оформить";
  buy.disabled = product.available === 0 || product.available === null;
  buy.addEventListener("click", () => purchase(product, Number(quantity.value), buy));
  buyRow.append(quantity, buy);
  card.append(sku, title, description, meta, buyRow);
  elements.catalogGrid.append(card);
}

async function purchase(product, quantity, button) {
  elements.orderFeedback.hidden = true;
  if (!state.token) {
    elements.loginForm.scrollIntoView({ behavior: "smooth", block: "center" });
    elements.loginError.textContent = "Войдите, чтобы оформить заказ.";
    elements.loginError.hidden = false;
    return;
  }
  if (!Number.isInteger(quantity) || quantity < 1) {
    showFeedback("Количество должно быть положительным целым числом.", true);
    return;
  }
  button.disabled = true;
  const originalText = button.textContent;
  button.textContent = "Оформляем…";
  let reservation = null;
  try {
    reservation = await api(endpoints.reservations, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json", "Idempotency-Key": idempotencyKey() }),
      body: JSON.stringify({ product_id: product.id, quantity }),
    });
    const order = await api(endpoints.orders, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json", "Idempotency-Key": idempotencyKey() }),
      body: JSON.stringify({ reservation_id: reservation.id }),
    });
    showFeedback(`Заказ ${order.id} успешно создан.`);
    await Promise.all([loadCatalog(), loadOrders()]);
  } catch (error) {
    if (reservation?.id) {
      await fetch(`${endpoints.reservations}/${reservation.id}/release`, {
        method: "POST",
        headers: authHeaders(),
      }).catch(() => null);
    }
    showFeedback(error.status === 409 ? "Недостаточно товара для выбранного количества." : `Не удалось оформить заказ: ${error.message}`, true);
  } finally {
    button.disabled = false;
    button.textContent = originalText;
  }
}

async function loadOrders() {
  if (!state.token) return;
  elements.ordersStatus.textContent = "Загружаем заказы…";
  elements.ordersList.replaceChildren();
  try {
    const orders = await api(endpoints.orders, { headers: authHeaders() });
    elements.ordersStatus.textContent = orders.length ? "" : "Заказов пока нет.";
    orders.forEach((order) => {
      const card = document.createElement("article");
      card.className = "order-card";
      card.dataset.testid = "order-card";
      const id = document.createElement("span");
      id.className = "order-id";
      id.textContent = order.id;
      const amount = document.createElement("strong");
      amount.textContent = `${order.total_amount} ₽`;
      const status = document.createElement("span");
      status.className = "order-status";
      status.textContent = order.status === "created" ? "Создан" : "Отменён";
      card.append(id, amount, status);
      elements.ordersList.append(card);
    });
  } catch (error) {
    elements.ordersStatus.textContent = `Не удалось загрузить заказы: ${error.message}`;
  }
}

elements.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.loginError.hidden = true;
  const submit = elements.loginForm.querySelector("button[type=submit]");
  submit.disabled = true;
  const form = new FormData(elements.loginForm);
  const body = new URLSearchParams({ username: form.get("email"), password: form.get("password") });
  try {
    const token = await api(endpoints.token, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    state.token = token.access_token;
    sessionStorage.setItem("access_token", state.token);
    await loadSession();
    await loadCatalog();
  } catch (_) {
    elements.loginError.textContent = "Неверный email или пароль.";
    elements.loginError.hidden = false;
  } finally {
    submit.disabled = false;
  }
});

elements.logout.addEventListener("click", () => {
  clearSession();
  elements.loginForm.reset();
  elements.loginError.hidden = true;
  elements.loginForm.querySelector("input").focus();
});
elements.refresh.addEventListener("click", loadCatalog);

Promise.all([loadSession(), loadCatalog()]);
