import uuid
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Category, Product

SEED_CATEGORY_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
SEED_PRODUCT_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")


def seed() -> None:
    with SessionLocal() as database:
        category = database.scalar(select(Category).where(Category.id == SEED_CATEGORY_ID))
        if category is None:
            category = Category(id=SEED_CATEGORY_ID, name="Electronics", slug="electronics")
            database.add(category)
        product = database.scalar(select(Product).where(Product.id == SEED_PRODUCT_ID))
        if product is None:
            database.add(
                Product(
                    id=SEED_PRODUCT_ID,
                    sku="DEMO-HEADPHONES",
                    name="Demo Headphones",
                    description="Stable seed product for exploratory testing",
                    price=Decimal("79.90"),
                    category_id=SEED_CATEGORY_ID,
                    is_active=True,
                )
            )
        database.commit()


if __name__ == "__main__":
    seed()
