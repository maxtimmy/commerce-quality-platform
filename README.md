# Commerce Quality Platform

Воспроизводимый QA-стенд минимального интернет-магазина. Завершены Identity/Catalog API и отдельный Inventory API с JWT/RBAC, PostgreSQL, Redis и конкурентным резервированием. Полная тестовая стратегия и подтверждённые результаты дополняются по мере реализации этапов из [PLAN.md](PLAN.md).

## Быстрый запуск

Требуется Docker с Docker Compose.

```bash
docker compose up -d --build --wait
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8001/health
curl http://localhost:8001/ready
docker compose --profile qa run --rm --build qa
```

Остановка без удаления данных PostgreSQL:

```bash
docker compose down
```

## Текущая структура

- `app/` — Identity/Catalog API и общие модели;
- `inventory_service/` — отдельный Inventory API;
- `qa/` — независимый QA-код;
- `compose.yaml` — два API, PostgreSQL, Redis и запускаемый по профилю QA-контейнер;
- `SPEC.md`, `PLAN.md`, `STATUS.md` — требования, этапы и проверенный статус.

OpenAPI после запуска доступен по адресам `http://localhost:8000/openapi.json` и `http://localhost:8001/openapi.json`.

Полный прогон и отдельные suites:

```bash
docker compose --profile qa run --rm qa pytest -q
docker compose --profile qa run --rm qa pytest -m smoke -q
docker compose --profile qa run --rm qa pytest -m regression -q
docker compose --profile qa run --rm qa pytest --collect-only -q
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

Inventory и Identity/Catalog пока используют общий PostgreSQL-инстанс. Автоматическое истечение и commit резервов не реализованы — это граница следующего этапа Orders.

## Фактический статус

На 2026-10-01 собрано 98 содержательных тестов: 5 smoke и 93 regression. Полный suite прошёл на рабочем стенде и повторно после чистой миграции. Конкурентная проверка подтвердила ровно 5 успешных резервов при остатке 5 и 20 одновременных запросах; это результат локального стенда, не production-показатель. Реальные пользователи, бизнес-эффект и performance/DAST-результаты не заявляются. Подробности — в [STATUS.md](STATUS.md).
