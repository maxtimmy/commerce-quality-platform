import pytest
import schemathesis
from hypothesis import HealthCheck, settings

from qa.conftest import BASE_URL, INVENTORY_URL, ORDERS_URL, login_headers, ADMIN_EMAIL, ADMIN_PASSWORD


def load_schema(base_url: str, *, negative_only: bool):
    schema = schemathesis.openapi.from_url(f"{base_url}/openapi.json")
    modes = [
        schemathesis.GenerationMode.NEGATIVE
        if negative_only
        else schemathesis.GenerationMode.POSITIVE
    ]
    schema.config.generation.update(
        modes=modes,
        max_examples=10,
        deterministic=True,
        allow_extra_parameters=True,
    )
    schema.config.checks.update(
        included_check_names=[
            "not_a_server_error",
            "content_type_conformance",
            "response_schema_conformance",
            "negative_data_rejection",
        ]
    )
    return schema


api_reads = load_schema(BASE_URL, negative_only=False).include(method="GET")
api_writes = load_schema(BASE_URL, negative_only=True).exclude(method="GET")
inventory_reads = load_schema(INVENTORY_URL, negative_only=False).include(method="GET")
inventory_writes = load_schema(INVENTORY_URL, negative_only=True).exclude(method="GET")
orders_reads = load_schema(ORDERS_URL, negative_only=False).include(method="GET")
orders_writes = load_schema(ORDERS_URL, negative_only=True).exclude(method="GET")

property_settings = settings(
    max_examples=10,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow],
)


def admin_headers() -> dict[str, str]:
    return login_headers(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.mark.contract
@api_reads.parametrize()
@property_settings
def test_identity_catalog_read_contract(case) -> None:
    case.call_and_validate(headers=admin_headers())


@pytest.mark.contract
@api_writes.parametrize()
@property_settings
def test_identity_catalog_negative_contract(case) -> None:
    case.call_and_validate(headers=admin_headers())


@pytest.mark.contract
@inventory_reads.parametrize()
@property_settings
def test_inventory_read_contract(case) -> None:
    case.call_and_validate(headers=admin_headers())


@pytest.mark.contract
@inventory_writes.parametrize()
@property_settings
def test_inventory_negative_contract(case) -> None:
    case.call_and_validate(headers=admin_headers())


@pytest.mark.contract
@orders_reads.parametrize()
@property_settings
def test_orders_read_contract(case) -> None:
    case.call_and_validate(headers=admin_headers())


@pytest.mark.contract
@orders_writes.parametrize()
@property_settings
def test_orders_negative_contract(case) -> None:
    case.call_and_validate(headers=admin_headers())
