# Commerce Quality Platform

Воспроизводимый QA-стенд минимального интернет-магазина. Сейчас завершён первый этап: инфраструктурный каркас и health-check smoke test. Полная тестовая стратегия и подтверждённые результаты будут дополняться по мере реализации этапов из [PLAN.md](PLAN.md).

## Быстрый запуск

Требуется Docker с Docker Compose.

```bash
docker compose up -d --build --wait
curl http://localhost:8000/health
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

## Фактический статус

На 2026-09-30 собрано и успешно выполнено 1 содержательное smoke-тестирование. Production-нагрузка, реальные пользователи, бизнес-эффект и performance/DAST-результаты не заявляются. Подробности — в [STATUS.md](STATUS.md).
