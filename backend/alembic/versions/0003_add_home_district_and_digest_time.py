"""add home_district_id and digest_time to users

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-28
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "home_district_id",
            sa.Integer(),
            sa.ForeignKey("districts.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(op.f("ix_users_home_district_id"), "users", ["home_district_id"], unique=False)
    op.add_column(
        "users",
        sa.Column(
            "digest_time",
            sa.String(length=5),
            server_default="07:00",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "digest_time")
    op.drop_index(op.f("ix_users_home_district_id"), table_name="users")
    op.drop_column("users", "home_district_id")
