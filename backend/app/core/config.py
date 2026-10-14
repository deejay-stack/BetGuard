import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL, make_url

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


class ConfigurationError(ValueError):
    pass


SVM_SHADOW_VERSION = "optimized_svm_shadow_2026-10-11"
SVM_SHADOW_MANIFEST_SHA256 = "76d4bc7779b386c7d2c4be36ff59ee14f5093c533617ce42b6e046ae331574a1"


@dataclass(frozen=True)
class SVMShadowSettings:
    artifact_directory: Path
    manifest_sha256: str = SVM_SHADOW_MANIFEST_SHA256


def svm_shadow_settings() -> SVMShadowSettings | None:
    enabled = os.getenv("BETGUARD_SVM_SHADOW_ENABLED", "false").strip().lower()
    if enabled in {"false", "0"}:
        return None
    if enabled not in {"true", "1"}:
        raise ConfigurationError("BETGUARD_SVM_SHADOW_ENABLED must be true or false.")
    ml_root = Path(os.getenv("BETGUARD_ML_ROOT", Path(__file__).resolve().parents[3] / "ml"))
    return SVMShadowSettings((ml_root / "models" / SVM_SHADOW_VERSION).resolve())


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
