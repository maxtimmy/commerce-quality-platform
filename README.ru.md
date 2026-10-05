# Commerce Quality Platform

[English](README.md) | **Русский**

Воспроизводимый QA-стенд минимального интернет-магазина. Реализованы Identity/Catalog, Inventory и Orders API с JWT/RBAC, PostgreSQL, Redis, конкурентным резервированием, атомарным оформлением заказа, Web UI, кросс-браузерными E2E-тестами, Allure, Locust, безопасным OWASP ZAP DAST и раздельными GitHub Actions workflow. Полная тестовая стратегия и подтверждённые результаты дополняются по мере реализации этапов из [PLAN.md](PLAN.md).

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
- `compose.yaml` — три API, PostgreSQL, Redis, Web UI и профили QA/performance/security;
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

## Locust performance

Locust 2.46.5 запускается из закреплённого официального образа. Профиль создаёт изолированный товар `LOAD-<run-id>` с большим остатком, распределяет 20 пользователей как 14 читающих и 6 оформляющих, а после теста удаляет пользователей, заказы, резервы, остаток, товар, категорию и Redis-ключи.

Короткая проверка и основной профиль:

```bash
docker compose run --rm --build \
  -e LOAD_RUN_ID=smoke-local -e RESULTS_DIR=/results/smoke -e MIN_REQUESTS=1 \
  locust -f /mnt/locust/locustfile.py --headless \
  -u 2 -r 2 -t 15s --csv /results/smoke/stats --csv-full-history \
  --html /results/smoke/report.html --only-summary

docker compose run --rm --build \
  -e LOAD_RUN_ID=main-local -e RESULTS_DIR=/results/main \
  locust -f /mnt/locust/locustfile.py --headless \
  -u 20 -r 5 -t 2m --csv /results/main/stats --csv-full-history \
  --html /results/main/report.html --only-summary
```

Аварийная идемпотентная очистка доступна отдельно:

```bash
docker compose run --rm --build load-cleanup
```

Guardrails стенда: failure ratio ≤ 1%, aggregate p95 ≤ 1500 мс, read-only p95 ≤ 1000 мс, не менее 500 запросов, отсутствие HTTP 5xx и исключений Locust. HTML, CSV, JSON summary и параметры сохраняются в игнорируемом `performance-results/`.

## OWASP ZAP DAST

ZAP 2.17.0 выполняет только passive Web baseline и safe OpenAPI scans (`-S`); active scan, эксплуатация и внешние адреса исключены.

```bash
docker compose run --rm zap-web
docker compose run --rm zap-api
docker compose run --rm zap-api zap-api-scan.py \
  -t http://inventory-api:8001/openapi.json -f openapi -S \
  -c /zap/config/zap-api.conf \
  -r inventory-api.html -J inventory-api.json -w inventory-api.md -I
docker compose run --rm zap-api zap-api-scan.py \
  -t http://orders-api:8002/openapi.json -f openapi -S \
  -c /zap/config/zap-api.conf \
  -r orders-api.html -J orders-api.json -w orders-api.md -I
docker compose run --rm zap-check \
  security-results/web.json security-results/core-api.json \
  security-results/inventory-api.json security-results/orders-api.json
```

Каждый target создаёт HTML, JSON и Markdown в игнорируемом `security-results/`. Машинный triage блокирует новые Medium/High и технические ошибки; Low остаются WARN, Informational — INFO. Единственный исходный Medium от Web — отсутствие anti-CSRF token — явно классифицирован как неприменимый к bearer-аутентификации без cookie-сессии и остаётся видимым в отчёте. Это точечное обоснование, не глобальное исключение.

Отдельный `.github/workflows/nonfunctional.yml` запускается только вручную и параллельно выполняет performance и DAST в изолированных Compose-проектах. Артефакты хранятся 14 дней; secrets, Pages и deployment не используются. Workflow статически проверен, но внешний run не выполнялся.

## Финальный аудит одной командой

Финальный аудит использует отдельный Compose-проект, чистый PostgreSQL volume и host-порты `18000/18001/18002/18080`. Он пересобирает собственные образы без кэша, запускает все suites, создаёт Allure/Locust/ZAP-артефакты и проверяет очистку PostgreSQL/Redis. Audit volume гарантированно удаляется после завершения.

Команда требует чистое рабочее дерево и явное разрешение очистить только игнорируемые каталоги отчётов:

```bash
scripts/final-audit.sh --clean-artifacts
```

## OpenAPI contract testing

Schemathesis 4.10.2 загружает OpenAPI Identity/Catalog, Inventory и Orders. Suite содержит 27 собранных проверок — по одной на операцию; каждая выполняет до 10 детерминированных Hypothesis-примеров. GET проверяются positive-данными, изменяющие операции — negative-данными. Проверяются отсутствие 5xx, Content-Type, документированные response schemas и отклонение невалидных данных.

Неизвестные query-параметры разрешены генератору, поскольку текущий FastAPI-стенд их игнорирует. Проверка `status_code_conformance` пока не включена: не все доменные 401/403/404/409 перечислены в OpenAPI. Ограничения явные; server-error и response-schema проверки не отключены.

## Фактический статус

На 2026-10-05 собрано 164 содержательных теста: 7 smoke, 120 regression, 27 contract и 10 UI. Два последовательных полных Chromium-прогона дали `164 passed`; UI-suite отдельно дал по `10 passed` в Chromium, Firefox и WebKit. Основной локальный Locust-профиль выполнил 24 966 запросов при 208.38446412384073 RPS, failure ratio 0.0, median 2 мс, aggregate p95 7 мс и read-only p95 4 мс. Финальный ZAP triage: 0 блокирующих alerts, 3 WARN и 11 INFO. Это показатели конкретного локального Docker-стенда, не production SLA и не результаты реальных пользователей. Подробности — в [STATUS.md](STATUS.md).

## Лицензия

Проект распространяется по [лицензии MIT](LICENSE).
