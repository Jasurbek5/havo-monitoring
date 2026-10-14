"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at() -> sa.Column:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def upgrade() -> None:
    op.create_table(
        "districts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name_uz", sa.String(length=100), nullable=False),
        sa.Column("name_ru", sa.String(length=100), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("city_district", "region", name="districtkind", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("poll_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("alert_active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("last_alert_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_districts")),
        sa.UniqueConstraint("slug", name=op.f("uq_districts_slug")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("language", sa.String(length=2), server_default="uz", nullable=False),
        sa.Column("district_id", sa.Integer(), nullable=True),
        sa.Column("alert_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("daily_digest", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["district_id"],
            ["districts.id"],
            name=op.f("fk_users_district_id_districts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=True)
    op.create_index(op.f("ix_users_district_id"), "users", ["district_id"], unique=False)

    op.create_table(
        "air_quality_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("district_id", sa.Integer(), nullable=False),
        sa.Column("aqi", sa.Integer(), nullable=False),
        sa.Column("pm2_5", sa.Float(), nullable=True),
        sa.Column("pm10", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["district_id"],
            ["districts.id"],
            name=op.f("fk_air_quality_logs_district_id_districts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_air_quality_logs")),
        sa.UniqueConstraint(
            "district_id", "recorded_at", name="uq_air_quality_logs_district_recorded"
        ),
    )
    op.create_index(
        op.f("ix_air_quality_logs_recorded_at"), "air_quality_logs", ["recorded_at"], unique=False
    )

    op.create_table(
        "complaints",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("district_id", sa.Integer(), nullable=True),
        sa.Column(
            "category",
            sa.Enum(
                "burning",
                "industrial",
                "smoke_dust",
                "transport",
                "other",
                name="complaintcategory",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "new",
                "in_progress",
                "resolved",
                name="complaintstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("location_is_approx", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("photo_file_id", sa.String(length=255), nullable=True),
        sa.Column("photo_path", sa.String(length=255), nullable=True),
        sa.Column("admin_note", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_complaints_user_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["district_id"],
            ["districts.id"],
            name=op.f("fk_complaints_district_id_districts"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_complaints")),
    )
    op.create_index(op.f("ix_complaints_user_id"), "complaints", ["user_id"], unique=False)
    op.create_index(op.f("ix_complaints_district_id"), "complaints", ["district_id"], unique=False)
    op.create_index(op.f("ix_complaints_status"), "complaints", ["status"], unique=False)

    op.create_table(
        "admin_users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        _created_at(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_users")),
        sa.UniqueConstraint("username", name=op.f("uq_admin_users_username")),
    )


def downgrade() -> None:
    op.drop_table("admin_users")
    op.drop_index(op.f("ix_complaints_status"), table_name="complaints")
    op.drop_index(op.f("ix_complaints_district_id"), table_name="complaints")
    op.drop_index(op.f("ix_complaints_user_id"), table_name="complaints")
    op.drop_table("complaints")
    op.drop_index(op.f("ix_air_quality_logs_recorded_at"), table_name="air_quality_logs")
    op.drop_table("air_quality_logs")
    op.drop_index(op.f("ix_users_district_id"), table_name="users")
    op.drop_index(op.f("ix_users_telegram_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("districts")
