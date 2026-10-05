from contextlib import nullcontext

from alembic import context
from sqlalchemy import inspect, text

from app.core.config import ConfigurationError
from app.core.database import SCHEMA, make_engine
from app.models import Base


def include_name(name, type_, _parent_names):
    # Autogenerate must never propose dropping Supabase-managed or unrelated
    # tables simply because they are absent from this application's metadata.
    if type_ == "schema":
        return name == SCHEMA
    if type_ == "table":
        return name == "domain_catalog"
    return True


def run():
    if context.is_offline_mode():
        raise ConfigurationError("Run migrations online so existing tables can be inspected first.")
    supplied_connection = context.config.attributes.get("connection")
    engine = None if supplied_connection is not None else make_engine(migration=True)
    try:
        with (nullcontext(supplied_connection) if supplied_connection is not None else engine.connect()) as connection:
            inspector = inspect(connection)
            # Never silently create a second catalog or stamp an existing schema.
            for schema in inspector.get_schema_names():
                if schema.startswith("pg_") or schema == "information_schema":
                    continue
                names = inspector.get_table_names(schema=schema)
                if "domain_catalog" in names and (
                    schema != SCHEMA or "alembic_version" not in names
                ):
                    raise ConfigurationError("Existing unmanaged domain_catalog found. Inspect and reconcile it before migrating; no changes applied.")
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
            connection.execute(text(f'REVOKE ALL ON SCHEMA "{SCHEMA}" FROM PUBLIC'))
            context.configure(connection=connection, target_metadata=Base.metadata,
                              version_table_schema=SCHEMA, include_schemas=True,
                              include_name=include_name)
            with context.begin_transaction():
                context.run_migrations()
            if supplied_connection is None:
                connection.commit()
    finally:
        if engine is not None:
            engine.dispose()


try:
    run()
except ConfigurationError:
    raise
except Exception:
    raise ConfigurationError("Migration failed; transaction rolled back. Check private connection settings, role privileges and schema inspection. Database details are suppressed.") from None
