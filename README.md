# Commerce Quality Platform

Воспроизводимый QA-стенд минимального интернет-магазина. Реализованы Identity/Catalog, Inventory и Orders API с JWT/RBAC, PostgreSQL, Redis, конкурентным резервированием, атомарным оформлением заказа и минимальным Web UI с Chromium E2E-тестами. Полная тестовая стратегия и подтверждённые результаты дополняются по мере реализации этапов из [PLAN.md](PLAN.md).

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

QA-образ основан на официальном Playwright Python `v1.63.0-noble`; Python-пакет `playwright==1.63.0` совпадает с версией образа. UI-suite использует только Chromium. Desktop/mobile viewport, клавиатурный вход и отсутствие необработанных JavaScript-ошибок проверяются автоматически. Screenshot, video и trace сохраняются в игнорируемый каталог `test-results/` только при падениях. Firefox/WebKit и браузерная матрица оставлены для этапа CI.

## OpenAPI contract testing

Schemathesis 4.10.2 загружает OpenAPI Identity/Catalog, Inventory и Orders. Suite содержит 27 собранных проверок — по одной на операцию; каждая выполняет до 10 детерминированных Hypothesis-примеров. GET проверяются positive-данными, изменяющие операции — negative-данными. Проверяются отсутствие 5xx, Content-Type, документированные response schemas и отклонение невалидных данных.

Неизвестные query-параметры разрешены генератору, поскольку текущий FastAPI-стенд их игнорирует. Проверка `status_code_conformance` пока не включена: не все доменные 401/403/404/409 перечислены в OpenAPI. Ограничения явные; server-error и response-schema проверки не отключены.

## Фактический статус

На 2026-10-04 собрано 164 содержательных теста: 7 smoke, 120 regression, 27 contract и 10 UI. Два последовательных полных прогона дали `164 passed`; UI-suite отдельно дал `10 passed`. Schemathesis обнаружил и помог исправить 500 при слишком большом `offset`; регрессионные проверки добавлены для Catalog и Orders. Конкурентные проверки подтвердили ровно 5 успешных резервов при остатке 5, единственный commit одного резерва и единственный заказ при повторе idempotency key. Это результаты локального стенда, не production-показатели. Реальные пользователи, бизнес-эффект и performance/DAST-результаты не заявляются. Подробности — в [STATUS.md](STATUS.md).
