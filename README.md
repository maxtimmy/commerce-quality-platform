# Commerce Quality Platform

Воспроизводимый QA-стенд минимального интернет-магазина. Завершены инфраструктурный каркас и PostgreSQL-каталог с независимыми API/интеграционными тестами. Полная тестовая стратегия и подтверждённые результаты дополняются по мере реализации этапов из [PLAN.md](PLAN.md).

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

Каталог доступен под `/api/v1/categories` и `/api/v1/products`. Пока JWT/RBAC не реализованы, изменяющие операции намеренно открыты; это ограничение будет устранено на этапе 3.

## Фактический статус

На 2026-10-01 собрано и успешно выполнено 33 содержательных теста: 2 smoke и 31 regression. Production-нагрузка, реальные пользователи, бизнес-эффект и performance/DAST-результаты не заявляются. Подробности — в [STATUS.md](STATUS.md).
