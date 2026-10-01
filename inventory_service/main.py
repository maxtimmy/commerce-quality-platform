import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from redis import Redis
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.config import settings
from app.database import engine, get_db
from app.models import InventoryStock, Product, Reservation
from inventory_service.schemas import ReservationCreate, ReservationOut, StockOut, StockSet
from inventory_service.security import Principal, get_principal, require_admin

app = FastAPI(
    title="Commerce Inventory API",
    description="Inventory and reservation service for the Commerce Quality Platform.",
    version="0.1.0",
)


def redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, socket_connect_timeout=1, decode_responses=True)


def cache_key(user_id: uuid.UUID, idempotency_key: str) -> str:
    return f"inventory:idem:{user_id}:{idempotency_key}"


def cache_reservation(user_id: uuid.UUID, idempotency_key: str, reservation_id: uuid.UUID) -> None:
    try:
        redis_client().setex(cache_key(user_id, idempotency_key), 600, str(reservation_id))
    except Exception:
        pass


def cached_reservation(
    database: Session, user_id: uuid.UUID, idempotency_key: str
) -> Reservation | None:
    try:
        reservation_id = redis_client().get(cache_key(user_id, idempotency_key))
        if reservation_id:
            return database.get(Reservation, uuid.UUID(reservation_id))
    except (Exception, ValueError):
        pass
    return None


def ensure_same_request(reservation: Reservation, payload: ReservationCreate) -> None:
    if reservation.product_id != payload.product_id or reservation.quantity != payload.quantity:
        raise HTTPException(status_code=409, detail="Idempotency key was used with different payload")


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "inventory-api"}


@app.get("/ready", tags=["system"])
def readiness() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        redis_client().ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Service dependencies are unavailable") from exc
    return {"status": "ready", "postgres": "ok", "redis": "ok"}


@app.get("/api/v1/inventory/{product_id}", response_model=StockOut, tags=["inventory"])
def get_stock(product_id: uuid.UUID, database: Session = Depends(get_db)) -> InventoryStock:
    stock = database.get(InventoryStock, product_id)
    if stock is None:
        raise HTTPException(status_code=404, detail="Inventory not found")
    return stock


@app.put("/api/v1/inventory/{product_id}", response_model=StockOut, tags=["inventory"])
def set_stock(
    product_id: uuid.UUID,
    payload: StockSet,
    database: Session = Depends(get_db),
    _admin: Principal = Depends(require_admin),
) -> InventoryStock:
    if database.get(Product, product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")
    stock = database.scalar(
        select(InventoryStock).where(InventoryStock.product_id == product_id).with_for_update()
    )
    if stock is None:
        stock = InventoryStock(
            product_id=product_id,
            available_quantity=payload.quantity,
            reserved_quantity=0,
            version=1,
        )
        database.add(stock)
    else:
        if payload.quantity < stock.reserved_quantity:
            raise HTTPException(status_code=409, detail="Quantity is below the reserved amount")
        stock.available_quantity = payload.quantity - stock.reserved_quantity
        stock.version += 1
    database.commit()
    database.refresh(stock)
    return stock


@app.post(
    "/api/v1/reservations",
    response_model=ReservationOut,
    status_code=status.HTTP_201_CREATED,
    tags=["reservations"],
)
def reserve(
    payload: ReservationCreate,
    response: Response,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$"
    ),
    database: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Reservation:
    existing = cached_reservation(database, principal.user_id, idempotency_key)
    if existing is not None:
        ensure_same_request(existing, payload)
        response.status_code = status.HTTP_200_OK
        return existing

    lock_value = f"{principal.user_id}:{idempotency_key}"
    database.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_value, 0))"),
        {"lock_value": lock_value},
    )
    existing = database.scalar(
        select(Reservation).where(
            Reservation.user_id == principal.user_id,
            Reservation.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        ensure_same_request(existing, payload)
        database.commit()
        cache_reservation(principal.user_id, idempotency_key, existing.id)
        response.status_code = status.HTTP_200_OK
        return existing

    if database.get(Product, payload.product_id) is None:
        raise HTTPException(status_code=404, detail="Product not found")
    statement = (
        update(InventoryStock)
        .where(
            InventoryStock.product_id == payload.product_id,
            InventoryStock.available_quantity >= payload.quantity,
        )
        .values(
            available_quantity=InventoryStock.available_quantity - payload.quantity,
            reserved_quantity=InventoryStock.reserved_quantity + payload.quantity,
            version=InventoryStock.version + 1,
            updated_at=datetime.now(timezone.utc),
        )
        .returning(InventoryStock.product_id)
    )
    if database.execute(statement).scalar_one_or_none() is None:
        stock = database.get(InventoryStock, payload.product_id)
        if stock is None:
            raise HTTPException(status_code=404, detail="Inventory not found")
        raise HTTPException(status_code=409, detail="Insufficient inventory")

    reservation = Reservation(
        product_id=payload.product_id,
        user_id=principal.user_id,
        quantity=payload.quantity,
        status="active",
        idempotency_key=idempotency_key,
    )
    database.add(reservation)
    database.commit()
    database.refresh(reservation)
    cache_reservation(principal.user_id, idempotency_key, reservation.id)
    return reservation


@app.post(
    "/api/v1/reservations/{reservation_id}/release",
    response_model=ReservationOut,
    tags=["reservations"],
)
def release(
    reservation_id: uuid.UUID,
    database: Session = Depends(get_db),
    principal: Principal = Depends(get_principal),
) -> Reservation:
    reservation = database.scalar(
        select(Reservation).where(Reservation.id == reservation_id).with_for_update()
    )
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found")
    if principal.role != "admin" and reservation.user_id != principal.user_id:
        raise HTTPException(status_code=403, detail="Reservation belongs to another user")
    if reservation.status == "released":
        database.commit()
        return reservation

    database.execute(
        update(InventoryStock)
        .where(InventoryStock.product_id == reservation.product_id)
        .values(
            available_quantity=InventoryStock.available_quantity + reservation.quantity,
            reserved_quantity=InventoryStock.reserved_quantity - reservation.quantity,
            version=InventoryStock.version + 1,
            updated_at=datetime.now(timezone.utc),
        )
    )
    reservation.status = "released"
    reservation.released_at = datetime.now(timezone.utc)
    database.commit()
    database.refresh(reservation)
    return reservation
