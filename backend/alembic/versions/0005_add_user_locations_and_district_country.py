"""add user_locations and district country

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-01
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("districts", sa.Column("country", sa.String(length=100), nullable=True))
    op.add_column("districts", sa.Column("admin_area", sa.String(length=100), nullable=True))

    op.create_table(
        "user_locations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("district_id", sa.Integer(), nullable=False),
        sa.Column("is_home", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("custom_name", sa.String(length=100), nullable=True),
        sa.Column("order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["district_id"], ["districts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_locations_user_id"), "user_locations", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_locations_district_id"), "user_locations", ["district_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_locations_district_id"), table_name="user_locations")
    op.drop_index(op.f("ix_user_locations_user_id"), table_name="user_locations")
    op.drop_table("user_locations")
    op.drop_column("districts", "admin_area")
    op.drop_column("districts", "country")
