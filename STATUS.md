# Commerce Quality Platform — статус

Обновлено: 2026-10-04

## Текущий этап

Этап 7 — минимальный Web UI и Playwright: завершён.

## Готово

- Согласованы назначение, границы и целевая архитектура.
- Работа разбита на десять проверяемых этапов.
- Зафиксированы правила честного подсчёта тестов и результатов.
- Создано минимальное FastAPI-приложение с `/health` и OpenAPI.
- Создан Compose-стенд из API, PostgreSQL и Redis и отдельный QA-контейнер.
- Добавлен базовый smoke test на Pytest + requests.
- Добавлены Alembic-миграции, модели категорий и товаров и идемпотентные seed-данные.
- Реализован CRUD категорий и товаров, пагинация, фильтры и поиск.
- Добавлен `/ready` с проверкой PostgreSQL и Redis.
- QA-контейнер выполняет независимые API- и интеграционные проверки с очисткой тестовых данных.
- Добавлены регистрация customer, OAuth2 password login и endpoint текущего пользователя.
- Пароли хешируются Argon2; HS256 JWT действует 15 минут.
- Публичная регистрация не позволяет назначить роль; локальный admin создаётся seed-процессом.
- Все изменяющие операции каталога защищены ролью `admin`, чтение осталось публичным.
- Добавлен отдельный `inventory-api` контейнер с собственными health, readiness и OpenAPI.
- Реализованы остатки, атомарные reserve/release, PostgreSQL idempotency и Redis TTL-кэш.
- Добавлены ограничения БД от отрицательных количеств и защита удаления товара с inventory-записями.
- QA-покрытие включает API, PostgreSQL, Redis и конкурентные запросы.
- Добавлен отдельный `orders-api` контейнер с health, readiness и OpenAPI на порту 8002.
- Реализованы создание, список, чтение и отмена заказов с owner/admin-доступом.
- Commit активного резерва, изменение остатка и создание заказа выполняются одной PostgreSQL-транзакцией.
- Цена фиксируется в заказе; создание и отмена идемпотентны, committed-резерв нельзя освободить через Inventory.
- Конкурентные попытки оформить один резерв создают ровно один заказ.
- Добавлен отдельный contract suite на Schemathesis для 27 операций трёх OpenAPI-схем.
- GET проверяются positive property-based примерами, изменяющие операции — negative примерами без загрязнения данными.
- Schemathesis обнаружил 500 на слишком большом `offset`; верхняя граница добавлена в Catalog и Orders и закреплена регрессионными тестами.
- Добавлен отдельный `web`-контейнер с Nginx, healthcheck и статическим адаптивным UI на порту 8080.
- Nginx проксирует три API через единый origin; CORS в API не добавлялся.
- UI реализует публичный каталог, вход/logout, reserve → order, список заказов и безопасное отображение ошибок.
- JWT хранится в `sessionStorage`; reserve/order используют независимые idempotency keys, а ошибка order запускает best-effort release.
- QA-образ переведён на Playwright Python `v1.63.0-noble` с совпадающим пакетом `playwright==1.63.0`.
- Добавлены 10 независимых Chromium UI-тестов, включая desktop/mobile, клавиатуру, stale stock, компенсацию и повторное действие.

## Проверено

- Рабочий каталог изначально пуст; существующих пользовательских файлов и изменений нет.
- В окружении доступны Docker 29.8.0, Docker Compose 5.5.1 и Python 3.9.6.
- `docker compose config --quiet` — успешно.
- `docker compose up -d --build --wait` — API, PostgreSQL и Redis перешли в `healthy`.
- `GET http://localhost:8000/health` — HTTP 200, `{"status":"ok","service":"commerce-api"}`.
- Smoke suite в отдельном QA-контейнере — `1 passed`.
- На этапе 1 сбор тестов составлял `1 test collected`.
- Полный suite этапа 2 — `33 passed`.
- Smoke suite — `2 passed, 31 deselected`.
- Regression suite — `31 passed, 2 deselected`.
- Сбор тестов — `33 tests collected`.
- Повторный запуск миграций и seed сохранил ровно одну демонстрационную категорию и один товар.
- При остановленном Redis `/ready` вернул HTTP 503; после запуска Redis стенд вернулся в `healthy`.
- Два последовательных полных прогона этапа 3 — по `66 passed`.
- Smoke suite — `3 passed, 63 deselected`.
- Regression suite — `63 passed, 3 deselected`.
- Сбор тестов — `66 tests collected`.
- Миграция БД находится на ревизии `0002`; после suite осталось 0 тестовых пользователей.
- OpenAPI содержит OAuth2 password flow и security-требования только у защищённых операций.
- После перезапуска seed сохранил ровно одного admin, одну демонстрационную категорию и один товар.
- После удаления проектного PostgreSQL-volume стенд заново применил миграции до `0002`, создал по одной seed-записи и выполнил `66 passed`.
- Полный прогон этапа 4 — `98 passed`; повторный прогон после чистой установки — `98 passed`.
- Smoke suite — `5 passed, 93 deselected`.
- Regression suite — `93 passed, 5 deselected`.
- Сбор тестов — `98 tests collected`.
- При 20 конкурентных запросах на остаток 5 успешно ровно 5 резервов; БД зафиксировала `available=0`, `reserved=5`, без oversell.
- 10 конкурентных повторов одного idempotency key создали один резерв и списали остаток один раз.
- При остановленном Redis inventory readiness вернул 503, а replay восстановился из PostgreSQL с тем же reservation ID и без повторного списания.
- Чистый volume мигрирован до `0003`; seed создал остаток `25/0`, после suite осталось 0 тестовых резервов.
- Inventory OpenAPI отмечает публичный GET и защищённые PUT/reserve/release; все четыре основных сервиса healthy.
- Полный suite этапа 5 на рабочем стенде — `121 passed`; после расширения RBAC-проверок и чистой установки — `125 passed`.
- Smoke suite — `7 passed, 118 deselected`.
- Regression suite — `118 passed, 7 deselected`.
- Сбор тестов — `125 tests collected`.
- 10 конкурентных повторов одного order idempotency key вернули один order ID и создали одну запись.
- Две конкурентные попытки commit одного резерва создали ровно один заказ; вторая получила контролируемый 409.
- Миграция чистой БД дошла до `0004`; seed сохранил остаток `25/0`, после suite осталось 0 тестовых заказов и резервов.
- Orders OpenAPI содержит OAuth2 password flow и security у всех бизнес-операций; API, Inventory, Orders, PostgreSQL и Redis healthy.
- Два последовательных полных прогона этапа 6 — по `154 passed`.
- Smoke suite — `7 passed, 147 deselected`.
- Regression suite — `120 passed, 34 deselected`.
- Contract suite — `27 passed, 127 deselected`.
- Сбор тестов — `154 tests collected`; целевой порог ≥150 достигнут фактическим collection.
- После прогонов осталось 0 тестовых заказов, резервов, товаров, пользователей и Redis idempotency keys; пять сервисов healthy.
- UI suite — `10 passed, 154 deselected`.
- Два последовательных полных прогона этапа 7 — по `164 passed`.
- Smoke suite — `7 passed, 157 deselected`.
- Regression suite — `120 passed, 44 deselected`.
- Contract suite — `27 passed, 137 deselected`.
- Сбор тестов — `164 tests collected`: 154 API/contract/integration и 10 UI-проверок.
- Страница и `/health` доступны с хоста и из QA-контейнера; desktop 1440×1000 и mobile 390×844 проверены визуально.
- API, Inventory, Orders, Web, PostgreSQL и Redis находятся в `healthy`.
- После всех прогонов осталось 0 тестовых пользователей, товаров, резервов, заказов и 0 Redis-ключей.

## Следующий этап

Этап 8: Allure и параллельный матричный GitHub Actions с отдельными suites и браузерами.

## Ограничения и честные метрики

- Подтверждённых production-показателей и реальных пользователей нет.
- На текущем этапе собрано 164 содержательных автопроверки; целевой минимум ≥150 достигнут.
- Compose содержит только локальные демонстрационные JWT/admin credentials; они не предназначены для production.
- Refresh tokens, logout, восстановление пароля, подтверждение email и rate limiting не реализованы.
- Inventory и Identity/Catalog пока используют общий PostgreSQL-инстанс; отдельные БД не заявляются.
- Автоматическое истечение резервов, платежи и доставка не реализованы.
- Нагрузочные и DAST-результаты ещё не получены.
- OpenAPI пока не перечисляет все доменные 401/403/404/409 responses, поэтому Schemathesis `status_code_conformance` явно отложен до расширения error-контрактов.
- Неизвестные query-параметры FastAPI игнорирует; contract generation считает их допустимыми и продолжает проверять объявленные типы и границы.
- UI проверен только в Chromium. Firefox/WebKit и браузерная CI-матрица относятся к этапу 8.
- UI — учебный QA-стенд без frontend-фреймворка, production-аутентификации и заявлений о реальной эксплуатации.
