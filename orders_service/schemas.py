import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reservation_id: uuid.UUID


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    reservation_id: uuid.UUID
    product_id: uuid.UUID
    user_id: uuid.UUID
    quantity: int
    unit_price: Decimal
    total_amount: Decimal
    status: str
    created_at: datetime
    cancelled_at: datetime | None
