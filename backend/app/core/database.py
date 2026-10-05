from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.core.config import database_url

SCHEMA = "betguard_private"
REVISION = "0001_catalog"


def make_engine(*, migration: bool = False, value: str | None = None):
    options = {"poolclass": NullPool} if migration else {
        "pool_size": 3, "max_overflow": 0, "pool_timeout": 5,
        "pool_pre_ping": True, "pool_recycle": 300,
    }
    return create_engine(
        database_url(migration=migration, value=value),
        echo=False, hide_parameters=True,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=5000 -c lock_timeout=5000",
        },
        **options,
    )
