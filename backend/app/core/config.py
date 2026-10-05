import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class ConfigurationError(ValueError):
    pass


def database_url(*, migration: bool = False, value: str | None = None) -> URL:
    raw = value if value is not None else (
        os.getenv("MIGRATION_DATABASE_URL") if migration else None
    ) or os.getenv("DATABASE_URL", "")
    try:
        url = make_url(raw)
        if url.drivername in {"postgres", "postgresql"}:
            url = url.set(drivername="postgresql+psycopg")
        if (
            url.drivername != "postgresql+psycopg"
            or not url.host or not url.username or not url.password or not url.database
            or "<" in raw or ">" in raw
            or url.port == 6543
        ):
            raise ValueError()
        # These are the only accepted libpq URL options; connection timeouts and
        # server options below cannot be overridden through the URL.
        if set(url.query) - {"sslmode", "sslrootcert"}:
            raise ValueError()
        if url.query.get("sslmode") not in {"require", "verify-full"}:
            raise ValueError()
        cert = (
            os.getenv("MIGRATION_DATABASE_SSL_ROOT_CERT") if migration else None
        ) or os.getenv("DATABASE_SSL_ROOT_CERT") or url.query.get("sslrootcert")
        if url.query.get("sslmode") == "verify-full" and (
            not isinstance(cert, str) or not Path(cert).is_file()
        ):
            raise ValueError()
        if cert:
            url = url.update_query_dict({"sslrootcert": cert})
        return url
    except Exception:
        # Never include raw URLs, driver exceptions, or credentials in output.
        raise ConfigurationError(
            "Configure a PostgreSQL psycopg URL with a direct/session connection, "
            "sslmode=require or verify-full, and a valid CA file for verify-full. "
            "See backend/.env.example."
        ) from None
