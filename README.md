# Commerce Quality Platform

Воспроизводимый QA-стенд минимального интернет-магазина. Завершены инфраструктурный каркас, PostgreSQL-каталог и Identity с JWT/RBAC. Полная тестовая стратегия и подтверждённые результаты дополняются по мере реализации этапов из [PLAN.md](PLAN.md).

## Быстрый запуск

Требуется Docker с Docker Compose.

```bash
docker compose up -d --build --wait
curl http://localhost:8000/health
curl http://localhost:8000/ready
docker compose --profile qa run --rm --build qa
```

Остановка без удаления данных PostgreSQL:

```bash
docker compose down
```

## Текущая структура

- `app/` — тестируемое FastAPI-приложение;
- `qa/` — независимый QA-код;
- `compose.yaml` — API, PostgreSQL, Redis и запускаемый по профилю QA-контейнер;
- `SPEC.md`, `PLAN.md`, `STATUS.md` — требования, этапы и проверенный статус.

OpenAPI после запуска доступен по адресу `http://localhost:8000/openapi.json`.

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

## Фактический статус

На 2026-10-01 собрано и дважды успешно выполнено 66 содержательных тестов: 3 smoke и 63 regression. Production-нагрузка, реальные пользователи, бизнес-эффект и performance/DAST-результаты не заявляются. Подробности — в [STATUS.md](STATUS.md).
