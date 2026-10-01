import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Category, Product, User
from app.security import require_admin
from app.schemas import CategoryCreate, CategoryOut, CategoryUpdate, ProductCreate, ProductOut, ProductUpdate

router = APIRouter(prefix="/api/v1", tags=["catalog"])


def _commit(database: Session, conflict_message: str) -> None:
    try:
        database.commit()
    except IntegrityError as exc:
        database.rollback()
        raise HTTPException(status_code=409, detail=conflict_message) from exc


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryCreate,
    database: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Category:
    category = Category(**payload.model_dump())
    database.add(category)
    _commit(database, "Category name or slug already exists")
    database.refresh(category)
    return category


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(database: Session = Depends(get_db)) -> list[Category]:
    return list(database.scalars(select(Category).order_by(Category.slug)))


@router.get("/categories/{category_id}", response_model=CategoryOut)
def get_category(category_id: uuid.UUID, database: Session = Depends(get_db)) -> Category:
    category = database.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    database: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Category:
    category = database.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, field, value)
    _commit(database, "Category name or slug already exists")
    database.refresh(category)
    return category


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: uuid.UUID,
    database: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Response:
    category = database.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    database.delete(category)
    _commit(database, "Category is used by products")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    database: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Product:
    if database.get(Category, payload.category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    product = Product(**payload.model_dump())
    database.add(product)
    _commit(database, "Product SKU already exists")
    database.refresh(product)
    return product


@router.get("/products", response_model=list[ProductOut])
def list_products(
    database: Session = Depends(get_db),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    category_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    search: str | None = Query(default=None, min_length=1, max_length=160),
) -> list[Product]:
    query = select(Product)
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    if is_active is not None:
        query = query.where(Product.is_active == is_active)
    if search is not None:
        pattern = f"%{search}%"
        query = query.where(or_(Product.name.ilike(pattern), Product.sku.ilike(pattern)))
    query = query.order_by(Product.sku).offset(offset).limit(limit)
    return list(database.scalars(query))


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: uuid.UUID, database: Session = Depends(get_db)) -> Product:
    product = database.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: uuid.UUID,
    payload: ProductUpdate,
    database: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Product:
    product = database.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    changes = payload.model_dump(exclude_unset=True)
    if "category_id" in changes and database.get(Category, changes["category_id"]) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    for field, value in changes.items():
        setattr(product, field, value)
    _commit(database, "Product SKU already exists")
    database.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: uuid.UUID,
    database: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> Response:
    product = database.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    database.delete(product)
    database.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
