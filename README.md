# Commerce Quality Platform

Воспроизводимый QA-стенд минимального интернет-магазина. Реализованы Identity/Catalog, Inventory и Orders API с JWT/RBAC, PostgreSQL, Redis, конкурентным резервированием, атомарным оформлением заказа, Web UI, кросс-браузерными E2E-тестами, Allure и параллельным GitHub Actions workflow. Полная тестовая стратегия и подтверждённые результаты дополняются по мере реализации этапов из [PLAN.md](PLAN.md).

## Быстрый запуск

Требуется Docker с Docker Compose.

```bash
docker compose up -d --build --wait
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8001/health
curl http://localhost:8001/ready
curl http://localhost:8002/health
curl http://localhost:8002/ready
curl http://localhost:8080/health
docker compose --profile qa run --rm --build qa
```

Web UI после запуска доступен по адресу `http://localhost:8080`.

Остановка без удаления данных PostgreSQL:

```bash
docker compose down
```

## Текущая структура

- `app/` — Identity/Catalog API и общие модели;
- `inventory_service/` — отдельный Inventory API;
- `orders_service/` — отдельный Orders API;
- `web/` — статический HTML/CSS/JavaScript UI и Nginx reverse proxy;
- `qa/` — независимый QA-код;
- `compose.yaml` — три API, PostgreSQL, Redis, Web UI и запускаемый по профилю QA-контейнер;
- `SPEC.md`, `PLAN.md`, `STATUS.md` — требования, этапы и проверенный статус.

OpenAPI после запуска доступен по адресам `http://localhost:8000/openapi.json`, `http://localhost:8001/openapi.json` и `http://localhost:8002/openapi.json`.

Полный прогон и отдельные suites:

```bash
docker compose --profile qa run --rm qa pytest -q --browser chromium
docker compose --profile qa run --rm qa pytest -m smoke -q --browser chromium
docker compose --profile qa run --rm qa pytest -m regression -q --browser chromium
docker compose --profile qa run --rm qa pytest -m contract -q --browser chromium
docker compose --profile qa run --rm qa pytest -m ui -q --browser chromium \
  --tracing retain-on-failure --video retain-on-failure \
  --screenshot only-on-failure --output test-results
docker compose --profile qa run --rm qa pytest --collect-only -q --browser chromium
```

Allure results и локальный HTML-отчёт:

```bash
docker compose --profile qa run --rm qa pytest -m smoke -q \
  --alluredir=allure-results/smoke
docker compose --profile report run --rm --build allure-report \
  generate /allure-results --output /allure-report --clean
```

Готовый отчёт находится в `allure-report/index.html`. Генератор использует закреплённый Allure Report 2.46.1 и Java внутри Docker; установка на хост не требуется. `allure-results/`, `allure-report/` и `test-results/` не коммитятся.

Каталог доступен под `/api/v1/categories` и `/api/v1/products`. Чтение публичное; создание, изменение и удаление требуют роль `admin`.

## JWT и RBAC

Демонстрационные учётные данные из `compose.yaml` предназначены только для локального стенда:

- email: `admin@example.com`;
- пароль: `LocalAdmin123!`;
- JWT secret: `local-demo-secret-not-for-production`.

Получение токена и защищённый запрос:

```bash
curl -X POST http://localhost:8000/api/v1/auth/token \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'username=admin@example.com&password=LocalAdmin123!'

curl -X POST http://localhost:8000/api/v1/categories \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{"name":"Books","slug":"books"}'
```

Матрица доступа:

| Операция | Без токена | customer | admin |
|---|---:|---:|---:|
| Чтение каталога | 200 | 200 | 200 |
| Изменение каталога | 401 | 403 | разрешено |
| `/auth/me` | 401 | 200 | 200 |

Access token действует 15 минут. Refresh tokens, logout, восстановление пароля, подтверждение email и rate limiting пока не реализованы.

## Inventory и резервирование

Публичное чтение остатка:

```bash
curl http://localhost:8001/api/v1/inventory/20000000-0000-0000-0000-000000000001
```

Создание и освобождение резерва с токеном customer или admin:

```bash
curl -X POST http://localhost:8001/api/v1/reservations \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' \
  -H 'Idempotency-Key: example-reservation-1' \
  -H 'Content-Type: application/json' \
  -d '{"product_id":"20000000-0000-0000-0000-000000000001","quantity":2}'

curl -X POST http://localhost:8001/api/v1/reservations/<RESERVATION_ID>/release \
  -H 'Authorization: Bearer <ACCESS_TOKEN>'
```

PostgreSQL является источником истины. Redis хранит idempotency mapping в течение 10 минут; при его недоступности reserve/replay продолжает работать через PostgreSQL, но `/ready` Inventory возвращает 503.

Inventory, Orders и Identity/Catalog пока используют общий PostgreSQL-инстанс. Это позволяет оформить резерв одной транзакцией без заявления распределённых транзакций.

## Orders

Создание заказа из активного резерва:

```bash
curl -X POST http://localhost:8002/api/v1/orders \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' \
  -H 'Idempotency-Key: example-order-1' \
  -H 'Content-Type: application/json' \
  -d '{"reservation_id":"<RESERVATION_ID>"}'

curl http://localhost:8002/api/v1/orders \
  -H 'Authorization: Bearer <ACCESS_TOKEN>'

curl -X POST http://localhost:8002/api/v1/orders/<ORDER_ID>/cancel \
  -H 'Authorization: Bearer <ACCESS_TOKEN>'
```

Commit переводит резерв в `committed`, убирает количество из зарезервированного остатка и фиксирует цену в заказе. Повтор с тем же idempotency key не создаёт второй заказ. Отмена владельцем или admin идемпотентно возвращает количество в доступный остаток. Платежи, доставка и автоматическое истечение резервов пока не реализованы.

## Web UI и Playwright

Nginx раздаёт адаптивный статический UI на порту `8080` и проксирует API в рамках одного origin: Identity/Catalog через `/gateway/core`, Inventory через `/gateway/inventory`, Orders через `/gateway/orders`. CORS в API не требуется. Интерфейс поддерживает вход, публичный каталог с остатками, reserve → order, список заказов и logout. JWT хранится только в `sessionStorage`; при logout и ответе 401 он удаляется. При ошибке создания заказа после успешного резерва UI пытается освободить резерв.

QA-образ основан на официальном Playwright Python `v1.63.0-noble`; Python-пакет `playwright==1.63.0` совпадает с версией образа. Один UI-suite выполняется в Chromium, Firefox и WebKit. Desktop/mobile viewport, клавиатурный вход и отсутствие необработанных JavaScript-ошибок проверяются автоматически. Screenshot, video и trace сохраняются в игнорируемый каталог `test-results/` только при падениях.

## Параллельный CI

Workflow `.github/workflows/qa.yml` запускается для push/pull request в `main` и вручную. Smoke, regression, contract и три UI-browser jobs используют отдельные GitHub-hosted runners и изолированные Compose-проекты. Каждый job сохраняет raw Allure results, а итоговый job собирает единый HTML artifact на 14 дней. GitHub Pages, deployment и secrets не используются.

Workflow проверен локально `actionlint 1.7.12`; фактический запуск GitHub Actions пока не выполнялся, поскольку у локального репозитория нет remote и проект не публиковался.

## OpenAPI contract testing

Schemathesis 4.10.2 загружает OpenAPI Identity/Catalog, Inventory и Orders. Suite содержит 27 собранных проверок — по одной на операцию; каждая выполняет до 10 детерминированных Hypothesis-примеров. GET проверяются positive-данными, изменяющие операции — negative-данными. Проверяются отсутствие 5xx, Content-Type, документированные response schemas и отклонение невалидных данных.

Неизвестные query-параметры разрешены генератору, поскольку текущий FastAPI-стенд их игнорирует. Проверка `status_code_conformance` пока не включена: не все доменные 401/403/404/409 перечислены в OpenAPI. Ограничения явные; server-error и response-schema проверки не отключены.

## Фактический статус

На 2026-10-04 собрано 164 содержательных теста: 7 smoke, 120 regression, 27 contract и 10 UI. Два последовательных полных Chromium-прогона дали `164 passed`; UI-suite отдельно дал по `10 passed` в Chromium, Firefox и WebKit. Чистый Allure-отчёт содержит 184 успешных выполнения с учётом трёх браузеров — это не 184 разных теста. Schemathesis обнаружил и помог исправить 500 при слишком большом `offset` и NUL в OAuth2 username. Это результаты локального стенда, не production-показатели. Реальные пользователи, бизнес-эффект и performance/DAST-результаты не заявляются. Подробности — в [STATUS.md](STATUS.md).
