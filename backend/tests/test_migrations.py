"""Alembic migratsiyasi modellar bilan bir xil sxema yaratishini tekshiradi (SQLite'da)."""

from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.config import get_settings
from app.models import Base

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture
def alembic_cfg(tmp_path, monkeypatch):
    db_path = tmp_path / "migration.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    get_settings.cache_clear()
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    yield cfg, f"sqlite:///{db_path}"
    get_settings.cache_clear()


def test_upgrade_matches_models(alembic_cfg):
    cfg, sync_url = alembic_cfg
    command.upgrade(cfg, "head")

    engine = sa.create_engine(sync_url)
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)
    engine.dispose()
    assert diff == [], f"Migratsiya va modellar farq qiladi: {diff}"


def test_downgrade_removes_everything(alembic_cfg):
    cfg, sync_url = alembic_cfg
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    engine = sa.create_engine(sync_url)
    tables = set(sa.inspect(engine).get_table_names())
    engine.dispose()
    assert tables <= {"alembic_version"}
