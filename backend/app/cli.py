"""Run from backend: python -m app.cli inspect-db | import-catalog FILE."""
import argparse
import json
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import inspect, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.catalog import CatalogEntry
from app.core.config import ConfigurationError
from app.core.database import SCHEMA, make_engine
from app.models import DomainCatalog


def read_catalog(path: Path) -> list[CatalogEntry]:
    if path.stat().st_size > 5_000_000:
        raise ValueError("Catalog exceeds the 5 MB import limit; split it into reviewed batches.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not 1 <= len(data) <= 10_000:
        raise ValueError("Supply a JSON array containing 1 to 10,000 catalog entries.")
    entries = []
    seen = set()
    for index, row in enumerate(data, 1):
        try:
            entry = CatalogEntry.model_validate(row)
        except ValidationError:
            raise ValueError(f"Invalid catalog entry at row {index}. Check hostname, classification, provenance and review date.") from None
        if entry.hostname in seen:
            raise ValueError(f"Duplicate normalized hostname at row {index}; no entries imported.")
        seen.add(entry.hostname)
        entries.append(entry)
    return entries


def import_entries(connection, entries: list[CatalogEntry], *, update_existing=False):
    table = DomainCatalog.__table__
    if not update_existing and connection.execute(
        select(table.c.hostname).where(table.c.hostname.in_([e.hostname for e in entries])).limit(1)
    ).first():
        raise ValueError("Existing catalog entries found. Review the batch and use --update-existing only for intentional replacements.")
    for offset in range(0, len(entries), 500):
        statement = insert(table).values([e.model_dump() for e in entries[offset:offset + 500]])
        if update_existing:
            statement = statement.on_conflict_do_update(
                index_elements=[table.c.hostname],
                set_={key: getattr(statement.excluded, key) for key in (
                    "classification", "label_provenance", "review_status", "reviewed_at"
                )},
            )
        connection.execute(statement)


def inspect_database(connection):
    inspector = inspect(connection)
    tables = []
    for schema in inspector.get_schema_names():
        if schema.startswith("pg_") or schema == "information_schema":
            continue
        for name in inspector.get_table_names(schema=schema):
            tables.append({"schema": schema, "table": name,
                           "columns": [c["name"] for c in inspector.get_columns(name, schema=schema)]})
    security = connection.execute(text("""
        SELECT n.nspname AS schema, c.relname AS table, c.relrowsecurity AS rls,
               pg_get_userbyid(c.relowner) AS owner
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname=:schema AND c.relkind='r'
    """), {"schema": SCHEMA}).mappings().all()
    grants = connection.execute(text("""
        SELECT grantee, table_name, privilege_type FROM information_schema.table_privileges
        WHERE table_schema=:schema ORDER BY grantee, table_name, privilege_type
    """), {"schema": SCHEMA}).mappings().all()
    role = connection.execute(text("""
        SELECT rolname, rolsuper, rolbypassrls, rolcreaterole
        FROM pg_roles WHERE rolname=current_user
    """)).mappings().one()
    return {"tables": tables, "catalog_security": [dict(r) for r in security],
            "catalog_grants": [dict(r) for r in grants], "connected_role": dict(role)}


def main():
    parser = argparse.ArgumentParser(description="BetGuard catalog administration (no secrets in output).")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect-db", help="Read-only table/column and role/grant inventory; no row data.")
    importer = commands.add_parser("import-catalog")
    importer.add_argument("file", type=Path)
    importer.add_argument("--dry-run", action="store_true", help="Validate only; never connect.")
    importer.add_argument("--update-existing", action="store_true")
    args = parser.parse_args()
    engine = None
    try:
        entries = read_catalog(args.file) if args.command == "import-catalog" else []
        if args.command == "import-catalog" and args.dry_run:
            print(f"Validated {len(entries)} entries; no database connection made.")
            return
        engine = make_engine(migration=True)
        with engine.begin() as connection:
            if args.command == "inspect-db":
                print(json.dumps(inspect_database(connection), indent=2))
            else:
                import_entries(connection, entries, update_existing=args.update_existing)
        if args.command == "import-catalog":
            print(f"Imported {len(entries)} entries atomically.")
    except ConfigurationError as error:
        parser.exit(1, str(error) + "\n")
    except (OSError, UnicodeError, json.JSONDecodeError):
        parser.exit(1, "Could not read a valid UTF-8 JSON catalog file. No data imported.\n")
    except ValueError as error:
        parser.exit(1, str(error) + "\n")
    except SQLAlchemyError:
        parser.exit(1, "Database operation failed; import rolled back. Check configuration, migrations and privileges privately.\n")
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
