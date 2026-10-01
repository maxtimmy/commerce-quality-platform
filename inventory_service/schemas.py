import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StockSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(ge=0, le=2_000_000_000)


class StockOut(BaseModel):
    product_id: uuid.UUID
    available_quantity: int
    updated_at: datetime


class ReservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: uuid.UUID
    quantity: int = Field(gt=0, le=2_000_000_000)


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID
    user_id: uuid.UUID
    quantity: int
    status: str
    created_at: datetime
    released_at: datetime | None
    committed_at: datetime | None
