"""Create orders and support committed reservations."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_reservations_status", "reservations", type_="check")
    op.create_check_constraint(
        "ck_reservations_status",
        "reservations",
        "status IN ('active', 'released', 'committed')",
    )
    op.add_column("reservations", sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_orders_quantity_positive"),
        sa.CheckConstraint("unit_price >= 0", name="ck_orders_unit_price_nonnegative"),
        sa.CheckConstraint("total_amount >= 0", name="ck_orders_total_nonnegative"),
        sa.CheckConstraint("status IN ('created', 'cancelled')", name="ck_orders_status"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["reservation_id"], ["reservations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reservation_id", name="uq_orders_reservation_id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_orders_user_idempotency"),
    )
    op.create_index("ix_orders_product_id", "orders", ["product_id"])
    op.create_index("ix_orders_user_id", "orders", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_user_id", table_name="orders")
    op.drop_index("ix_orders_product_id", table_name="orders")
    op.drop_table("orders")
    op.drop_column("reservations", "committed_at")
    op.drop_constraint("ck_reservations_status", "reservations", type_="check")
    op.create_check_constraint(
        "ck_reservations_status", "reservations", "status IN ('active', 'released')"
    )
