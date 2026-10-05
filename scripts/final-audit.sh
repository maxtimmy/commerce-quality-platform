#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${1:-}" != "--clean-artifacts" || "$#" -ne 1 ]]; then
    echo "Usage: scripts/final-audit.sh --clean-artifacts" >&2
    exit 2
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

export COMPOSE_PROJECT_NAME=cqp-final-audit
export CORE_PORT=18000
export INVENTORY_PORT=18001
export ORDERS_PORT=18002
export WEB_PORT=18080

allure_container=cqp-final-allure-preview

cleanup() {
    exit_code=$?
    docker rm --force "$allure_container" >/dev/null 2>&1 || true
    docker compose --profile qa --profile report --profile performance --profile security \
        down --volumes --remove-orphans >/dev/null 2>&1 || true
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

run_qa() {
    docker compose --profile qa run --rm qa "$@"
}

assert_equals() {
    expected=$1
    actual=$2
    label=$3
    if [[ "$actual" != "$expected" ]]; then
        echo "$label: expected '$expected', got '$actual'" >&2
        exit 1
    fi
}

echo "[audit] preflight"
if [[ -n "$(git status --porcelain)" ]]; then
    echo "Final audit requires a clean Git working tree" >&2
    exit 1
fi
docker compose config --quiet
docker run --rm -v "$repo_dir:/repo" -w /repo rhysd/actionlint:1.7.12
python3 scripts/check-markdown-links.py

echo "[audit] clean ignored artifacts"
for directory in allure-results allure-report test-results performance-results security-results; do
    mkdir -p "$directory"
    find "$directory" -mindepth 1 -delete
done

echo "[audit] build from Dockerfiles without cache"
docker compose --profile qa --profile report --profile performance build --no-cache \
    api inventory-api orders-api web qa allure-report locust load-cleanup

echo "[audit] start a fresh isolated stack"
docker compose up --detach --wait
healthy_count="$(docker compose ps --format json | python3 -c \
    'import json,sys; print(sum(json.loads(line).get("Health") == "healthy" for line in sys.stdin if line.strip()))')"
assert_equals 6 "$healthy_count" "healthy service count"

echo "[audit] host endpoints, migrations and idempotent seed"
for url in \
    http://localhost:18000/health http://localhost:18000/ready \
    http://localhost:18001/health http://localhost:18001/ready \
    http://localhost:18002/health http://localhost:18002/ready \
    http://localhost:18080/health \
    http://localhost:18000/openapi.json \
    http://localhost:18001/openapi.json \
    http://localhost:18002/openapi.json; do
    curl --fail --silent --show-error "$url" >/dev/null
done
docker compose exec -T api alembic current | grep --quiet '0004'
docker compose exec -T api python -m app.seed
seed_state="$(docker compose exec -T postgres psql -U commerce -d commerce -At -F '|' -c \
    "SELECT
        (SELECT count(*) FROM users WHERE id='30000000-0000-0000-0000-000000000001'),
        (SELECT count(*) FROM categories WHERE id='10000000-0000-0000-0000-000000000001'),
        (SELECT count(*) FROM products WHERE id='20000000-0000-0000-0000-000000000001'),
        (SELECT available_quantity FROM inventory_stock WHERE product_id='20000000-0000-0000-0000-000000000001'),
        (SELECT reserved_quantity FROM inventory_stock WHERE product_id='20000000-0000-0000-0000-000000000001');")"
assert_equals '1|1|1|25|0' "$seed_state" "seed state"

echo "[audit] collection and marker suites with Allure"
collection_output="$(run_qa pytest --collect-only -q --browser chromium)"
echo "$collection_output"
grep --quiet '164 tests collected' <<<"$collection_output"
run_qa pytest -q -m smoke --browser chromium --alluredir=allure-results/smoke
run_qa pytest -q -m regression --browser chromium --alluredir=allure-results/regression
run_qa pytest -q -m contract --browser chromium --alluredir=allure-results/contract

echo "[audit] cross-browser UI"
for browser in chromium firefox webkit; do
    run_qa pytest -q -m ui --browser "$browser" \
        --alluredir="allure-results/ui-$browser" \
        --tracing retain-on-failure --video retain-on-failure \
        --screenshot only-on-failure --output "test-results/$browser"
done

echo "[audit] two complete Chromium runs"
run_qa pytest -q --browser chromium
run_qa pytest -q --browser chromium

echo "[audit] combined Allure report"
allure_count="$(find allure-results -name '*-result.json' -type f | wc -l | tr -d ' ')"
assert_equals 184 "$allure_count" "Allure execution count"
docker compose --profile report run --rm allure-report \
    generate /allure-results --output /allure-report --clean
test -s allure-report/index.html
docker run --rm --detach --name "$allure_container" -p 18088:80 \
    -v "$repo_dir/allure-report:/usr/share/nginx/html:ro" nginx:1.28-alpine >/dev/null
for _ in {1..20}; do
    if curl --fail --silent http://localhost:18088/ >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
curl --fail --silent --show-error http://localhost:18088/ >/dev/null
docker rm --force "$allure_container" >/dev/null

echo "[audit] Locust smoke and main profile"
run_id="$(date -u +%Y%m%d%H%M%S)"
docker compose run --rm \
    -e "LOAD_RUN_ID=final-smoke-$run_id" -e RESULTS_DIR=/results/smoke \
    -e MIN_REQUESTS=1 locust -f /mnt/locust/locustfile.py --headless \
    -u 2 -r 2 -t 15s --csv /results/smoke/stats --csv-full-history \
    --html /results/smoke/report.html --only-summary
docker compose run --rm \
    -e "LOAD_RUN_ID=final-main-$run_id" -e RESULTS_DIR=/results/main \
    locust -f /mnt/locust/locustfile.py --headless \
    -u 20 -r 5 -t 2m --csv /results/main/stats --csv-full-history \
    --html /results/main/report.html --only-summary
docker compose run --rm load-cleanup

echo "[audit] OWASP ZAP safe scans"
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

echo "[audit] residue and artifact checks"
residue="$(docker compose exec -T postgres psql -U commerce -d commerce -At -F '|' -c \
    "SELECT
        (SELECT count(*) FROM users WHERE email LIKE 'test-%@example.com' OR email LIKE 'load-%@example.com'),
        (SELECT count(*) FROM products WHERE sku LIKE 'TEST-%' OR sku LIKE 'LOAD-%'),
        (SELECT count(*) FROM categories WHERE slug LIKE 'test-%' OR slug LIKE 'load-%'),
        (SELECT count(*) FROM reservations),
        (SELECT count(*) FROM orders),
        (SELECT count(*) FROM reservations WHERE status='active');")"
assert_equals '0|0|0|0|0|0' "$residue" "test/load residue"
redis_keys="$(docker compose exec -T redis sh -c \
    "redis-cli --scan --pattern 'inventory:idem:*' | wc -l" | tr -d '[:space:]')"
assert_equals 0 "$redis_keys" "Redis idempotency key count"

for artifact in \
    allure-report/index.html \
    performance-results/smoke/report.html performance-results/smoke/summary.json \
    performance-results/main/report.html performance-results/main/summary.json \
    security-results/web.html security-results/web.json security-results/web.md \
    security-results/core-api.html security-results/core-api.json security-results/core-api.md \
    security-results/inventory-api.html security-results/inventory-api.json security-results/inventory-api.md \
    security-results/orders-api.html security-results/orders-api.json security-results/orders-api.md \
    security-results/summary.json; do
    test -s "$artifact"
done

docker compose logs --no-color > test-results/final-compose.log
docker compose config --quiet
docker run --rm -v "$repo_dir:/repo" -w /repo rhysd/actionlint:1.7.12
python3 scripts/check-markdown-links.py
git diff --check
test -z "$(git status --porcelain)"

printf '%s\n' \
    'Final audit passed' \
    'collection=164' \
    'allure_executions=184' \
    "compose_project=$COMPOSE_PROJECT_NAME" \
    > test-results/final-audit-summary.txt

echo "[audit] PASSED"
