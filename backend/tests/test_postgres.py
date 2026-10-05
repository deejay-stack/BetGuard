"""Opt-in ONLY: an empty dedicated test database/project; fixtures roll back."""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError

from app.schemas.catalog import CatalogEntry
from app.cli import import_entries
from app.core.config import database_url
from app.core.database import SCHEMA, make_engine
from app.models import DomainCatalog


def test_postgres_migrations_import_and_role_boundaries():
    raw = os.getenv("TEST_DATABASE_URL")
    if not raw or os.getenv("BETGUARD_TEST_DATABASE_CONFIRMED") != "yes":
        pytest.skip("Dedicated test database and explicit confirmation are not configured.")
    target = database_url(value=raw)
    # Fail closed on same endpoint or recognizable Supabase project, even if
    # runtime and migration use different users or direct/pooler hostnames.
    def project(url):
        if url.host.startswith("db.") and url.host.endswith(".supabase.co"):
            return url.host.split(".")[1]
        if url.host.endswith(".pooler.supabase.com") and "." in url.username:
            return url.username.rsplit(".", 1)[1]
        return None
    for key in ("DATABASE_URL", "MIGRATION_DATABASE_URL"):
        value = os.getenv(key)
        if value and "<" not in value:
            primary = database_url(value=value)
            target_project, primary_project = project(target), project(primary)
            if target_project is not None and primary_project is not None:
                # Different projects may legitimately share a regional pooler.
                assert target_project != primary_project, "Test project must be separate."
            else:
                assert not (target.host == primary.host and target.database == primary.database), "Test endpoint must be separate."
    engine = make_engine(migration=True, value=raw)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                assert SCHEMA not in inspect(connection).get_schema_names(), "Test database must have no existing BetGuard schema."
                cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
                cfg.attributes["connection"] = connection
                command.upgrade(cfg, "head")
                command.upgrade(cfg, "head")  # Repeat is non-destructive.
                row = CatalogEntry.model_validate({
                    "hostname": "fixture.example.test", "classification": "gambling",
                    "label_provenance": "synthetic integration fixture; test project only",
                    "review_status": "reviewed", "reviewed_at": "2026-01-01T00:00:00Z",
                })
                import_entries(connection, [row])
                original = connection.execute(select(DomainCatalog)).mappings().one()
                with pytest.raises(ValueError, match="Existing catalog"):
                    import_entries(connection, [row])
                revised = row.model_copy(update={"classification": "non_gambling"})
                import_entries(connection, [revised], update_existing=True)
                updated = connection.execute(select(DomainCatalog)).mappings().one()
                assert updated["classification"] == "non_gambling"
                assert updated["created_at"] == original["created_at"]
                with connection.begin_nested():
                    connection.execute(text("SET LOCAL ROLE betguard_reader"))
                    assert connection.execute(select(DomainCatalog.hostname)).scalar() == row.hostname
                    with pytest.raises(DBAPIError):
                        with connection.begin_nested():
                            connection.execute(text(f"DELETE FROM {SCHEMA}.domain_catalog"))
                    connection.execute(text("RESET ROLE"))
                for role in ("anon", "authenticated", "service_role"):
                    if connection.execute(text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}).scalar():
                        assert not connection.execute(text("SELECT has_schema_privilege(:role, :schema, 'USAGE')"), {"role": role, "schema": SCHEMA}).scalar()
                assert connection.execute(text(f"SELECT version_num FROM {SCHEMA}.alembic_version")).scalar() == "0001_catalog"
            finally:
                transaction.rollback()  # Includes DDL, roles and all fixtures.
    finally:
        engine.dispose()
