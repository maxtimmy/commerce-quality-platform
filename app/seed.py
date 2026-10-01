import uuid
from decimal import Decimal

from sqlalchemy import select

from app.database import SessionLocal
from app.config import settings
from app.models import Category, Product, User
from app.security import hash_password, verify_password

SEED_CATEGORY_ID = uuid.UUID("10000000-0000-0000-0000-000000000001")
SEED_PRODUCT_ID = uuid.UUID("20000000-0000-0000-0000-000000000001")
SEED_ADMIN_ID = uuid.UUID("30000000-0000-0000-0000-000000000001")


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
        admin = database.scalar(select(User).where(User.id == SEED_ADMIN_ID))
        if admin is None:
            database.add(
                User(
                    id=SEED_ADMIN_ID,
                    email=settings.admin_email.strip().lower(),
                    password_hash=hash_password(settings.admin_password),
                    role="admin",
                    is_active=True,
                )
            )
        else:
            admin.email = settings.admin_email.strip().lower()
            admin.role = "admin"
            admin.is_active = True
            if not verify_password(settings.admin_password, admin.password_hash):
                admin.password_hash = hash_password(settings.admin_password)
        database.commit()


if __name__ == "__main__":
    seed()
