import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response, status
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.models import InventoryStock, Order, Product, Reservation
from orders_service.schemas import OrderCreate, OrderOut
from orders_service.security import Principal, get_principal

app = FastAPI(
    title="Commerce Orders API",
    description="Order lifecycle service for the Commerce Quality Platform.",
    version="0.1.0",
)


def ensure_same_request(order: Order, payload: OrderCreate) -> None:
    if order.reservation_id != payload.reservation_id:
        raise HTTPException(status_code=409, detail="Idempotency key was used with different payload")


def can_access(order: Order, principal: Principal) -> bool:
    return principal.role == "admin" or order.user_id == principal.user_id


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "orders-api"}


@app.get("/ready", tags=["system"])
def readiness() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="PostgreSQL is unavailable") from exc
    return {"status": "ready", "postgres": "ok"}


@app.post(
    "/api/v1/orders",
    response_model=OrderOut,
    status_code=status.HTTP_201_CREATED,
    tags=["orders"],
)
def create_order(
    payload: OrderCreate,
    response: Response,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$"
    ),
    database: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Order:
    database.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:value, 0))"),
        {"value": f"order:{principal.user_id}:{idempotency_key}"},
    )
    existing = database.scalar(
        select(Order).where(
            Order.user_id == principal.user_id,
            Order.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        ensure_same_request(existing, payload)
        database.commit()
        response.status_code = status.HTTP_200_OK
        return existing

    reservation = database.scalar(
        select(Reservation).where(Reservation.id == payload.reservation_id).with_for_update()
    )
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if reservation.user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="Reservation belongs to another user")
    if reservation.status != "active":
        raise HTTPException(status_code=409, detail="Reservation is not active")

    product = database.get(Product, reservation.product_id)
    if product is None:
        raise HTTPException(status_code=409, detail="Reserved product no longer exists")
    stock_update = database.execute(
        update(InventoryStock)
        .where(
            InventoryStock.product_id == reservation.product_id,
            InventoryStock.reserved_quantity >= reservation.quantity,
        )
        .values(
            reserved_quantity=InventoryStock.reserved_quantity - reservation.quantity,
            version=InventoryStock.version + 1,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(InventoryStock.product_id)
    ).scalar_one_or_none()
    if stock_update is None:
        raise HTTPException(status_code=409, detail="Reservation inventory is inconsistent")

    now = datetime.now(timezone.utc)
    reservation.status = "committed"
    reservation.committed_at = now
    unit_price = Decimal(product.price)
    order = Order(
        reservation_id=reservation.id,
        product_id=reservation.product_id,
        user_id=principal.user_id,
        quantity=reservation.quantity,
        unit_price=unit_price,
        total_amount=unit_price * reservation.quantity,
        status="created",
        idempotency_key=idempotency_key,
    )
    database.add(order)
    database.commit()
    database.refresh(order)
    return order


@app.get("/api/v1/orders", response_model=list[OrderOut], tags=["orders"])
def list_orders(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    database: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> list[Order]:
    statement = select(Order).order_by(Order.created_at, Order.id).offset(offset).limit(limit)
    if principal.role != "admin":
        statement = statement.where(Order.user_id == principal.user_id)
    return list(database.scalars(statement))


@app.get("/api/v1/orders/{order_id}", response_model=OrderOut, tags=["orders"])
def get_order(
    order_id: uuid.UUID,
    database: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Order:
    order = database.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if not can_access(order, principal):
        raise HTTPException(status_code=403, detail="Order belongs to another user")
    return order


@app.post("/api/v1/orders/{order_id}/cancel", response_model=OrderOut, tags=["orders"])
def cancel_order(
    order_id: uuid.UUID,
    database: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Order:
    order = database.scalar(select(Order).where(Order.id == order_id).with_for_update())
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    if not can_access(order, principal):
        raise HTTPException(status_code=403, detail="Order belongs to another user")
    if order.status == "cancelled":
        database.commit()
        return order

    stock_update = database.execute(
        update(InventoryStock)
        .where(InventoryStock.product_id == order.product_id)
        .values(
            available_quantity=InventoryStock.available_quantity + order.quantity,
            version=InventoryStock.version + 1,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(InventoryStock.product_id)
    ).scalar_one_or_none()
    if stock_update is None:
        raise HTTPException(status_code=409, detail="Order inventory is missing")
    order.status = "cancelled"
    order.cancelled_at = datetime.now(timezone.utc)
    database.commit()
    database.refresh(order)
    return order
