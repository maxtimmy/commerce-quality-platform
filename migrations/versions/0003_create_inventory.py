"""Create inventory and reservation tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inventory_stock",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("available_quantity", sa.Integer(), nullable=False),
        sa.Column("reserved_quantity", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("available_quantity >= 0", name="ck_inventory_available_nonnegative"),
        sa.CheckConstraint("reserved_quantity >= 0", name="ck_inventory_reserved_nonnegative"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("product_id"),
    )
    op.create_table(
        "reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_reservations_quantity_positive"),
        sa.CheckConstraint("status IN ('active', 'released')", name="ck_reservations_status"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_reservations_user_idempotency"),
    )
    op.create_index("ix_reservations_product_id", "reservations", ["product_id"])
    op.create_index("ix_reservations_user_id", "reservations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_reservations_user_id", table_name="reservations")
    op.drop_index("ix_reservations_product_id", table_name="reservations")
    op.drop_table("reservations")
    op.drop_table("inventory_stock")
