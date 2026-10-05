import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.schemas.catalog import CatalogEntry, normalize_hostname
from app.services.catalog_service import classify
from app.cli import read_catalog
from app.core.config import ConfigurationError, database_url
from app.main import app
from app.services.model_service import ModelService


@pytest.fixture
def client():
    # Never touch developer credentials or any PostgreSQL database in unit tests.
    with patch("app.main.make_engine", side_effect=ConfigurationError("test")), patch("app.main.ModelService.from_environment", return_value=ModelService()), patch("app.main.load_runtime", return_value=None):
        with TestClient(app) as client:
            yield client


@pytest.mark.parametrize("value,expected", [
    ("HTTPS://EXAMPLE.COM./private?token=secret", "example.com"),
    (" www.Example.com ", "www.example.com"),
    ("https://bücher.example:443/a", "xn--bcher-kva.example"),
])
def test_normalization(value, expected):
    assert normalize_hostname(value) == expected


@pytest.mark.parametrize("value", ["", "localhost", "127.0.0.1", "https://[::1]", "ftp://example.com",
    "https://user:secret@example.com", "exa mple.com", "example.com:0", "example.com:",
    "example.com:65536", "https://ex%61mple.com", "-bad.example", "example.com\\evil", "example..com",
    "example.com\n.evil", "https://example.com:１２", "https://example.com:abc"])
def test_invalid_hostname(value):
    with pytest.raises(ValueError):
        normalize_hostname(value)


def entry(**overrides):
    return {"hostname": "EXAMPLE.test", "classification": "gambling", "label_provenance": "synthetic unit fixture",
            "review_status": "reviewed", "reviewed_at": "2026-01-01T00:00:00Z", **overrides}


@pytest.mark.parametrize("overrides", [
    {"reviewed_at": None}, {"review_status": "pending"}, {"classification": "safe"},
    {"label_provenance": " "}, {"reviewed_at": "2026-01-01T00:00:00"},
    {"reviewed_at": "2999-01-01T00:00:00Z"}, {"confidence": 0.99},
])
def test_import_rejects_invalid_review(overrides):
    with pytest.raises(ValueError):
        CatalogEntry.model_validate(entry(**overrides))


def test_only_reviewed_entries_are_definitive():
    reviewed = CatalogEntry.model_validate(entry())
    assert classify("example.test", reviewed).classification == "gambling"
    assert classify("missing.test", None).reason == "not_in_catalog"
    pending = CatalogEntry.model_validate(entry(review_status="pending", reviewed_at=None))
    assert classify("example.test", pending).classification == "unknown"
    assert classify("example.test", pending).label_provenance is None
    broken = SimpleNamespace(review_status="reviewed", reviewed_at=None)
    assert classify("example.test", broken).classification == "unknown"
    unknown = CatalogEntry.model_validate(entry(classification="unknown"))
    assert classify("example.test", unknown).classification == "unknown"


def test_import_validation_is_atomic_and_deduplicates_normalized_hosts(tmp_path):
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps([entry(), entry(hostname="https://example.test/path")]))
    with pytest.raises(ValueError, match="Duplicate normalized"):
        read_catalog(path)
    path.write_text(json.dumps([entry(), entry(hostname="invalid")]))
    with pytest.raises(ValueError, match="row 2"):
        read_catalog(path)
    path.write_text(json.dumps([entry()]))
    assert read_catalog(path)[0].hostname == "example.test"


@pytest.mark.parametrize("url", [
    "", "sqlite:///test.db", "postgresql://user:secret@host/db",
    "postgresql://user:secret@host/db?sslmode=disable",
    "postgresql://user:secret@host:6543/db?sslmode=require",
    "postgresql://user:secret@host/db?sslmode=require&options=unsafe",
    "postgresql://user:secret@host/db?sslmode=verify-full",
])
def test_unsafe_config_rejected_without_disclosing_secrets(url, monkeypatch):
    monkeypatch.delenv("DATABASE_SSL_ROOT_CERT", raising=False)
    with pytest.raises(ConfigurationError) as error:
        database_url(value=url)
    assert "secret" not in str(error.value)


def test_driver_tls_and_separate_migration_url(monkeypatch, tmp_path):
    cert = tmp_path / "ca.crt"
    cert.write_text("test file; no connection made")
    monkeypatch.setenv("DATABASE_SSL_ROOT_CERT", str(cert))
    monkeypatch.setenv("DATABASE_URL", "postgresql://reader:secret@host/db?sslmode=verify-full")
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql://owner:secret@host/db?sslmode=verify-full")
    assert database_url().drivername == "postgresql+psycopg"
    assert database_url().username == "reader"
    assert database_url(migration=True).username == "owner"
    assert database_url().query["sslrootcert"] == str(cert)


def test_health_without_database_and_private_errors(client):
    assert client.get("/health/live").json() == {"status": "ok"}
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert client.post("/v1/check", json={"hostname": "example.test"}).status_code == 503
    bad = client.post("/v1/check", json={"hostname": "https://user:my-secret@example.com"})
    assert bad.status_code == 422
    assert "my-secret" not in bad.text
    assert "confidence" not in bad.text


@pytest.mark.parametrize("row,classification,reason", [
    (None, "unknown", "not_in_catalog"),
    (SimpleNamespace(review_status="pending", reviewed_at=None), "unknown", "not_reviewed"),
    (SimpleNamespace(review_status="reviewed", reviewed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                     classification="non_gambling", label_provenance="test review"), "non_gambling", "reviewed_catalog"),
])
def test_check_contract(client, row, classification, reason):
    app.state.engine = MagicMock()
    with patch("app.services.catalog_service.Session") as session:
        session.return_value.__enter__.return_value.get.return_value = row
        response = client.post("/v1/check", json={"hostname": "HTTPS://EXAMPLE.test/path?secret=x"})
        assert response.status_code == 200
        assert response.json()["hostname"] == "example.test"
        assert response.json()["classification"] == classification
        assert response.json()["reason"] == reason
        assert response.headers["Cache-Control"] == "no-store"
        assert "secret" not in response.text


def test_database_errors_and_missing_migration_are_unavailable(client):
    app.state.engine = MagicMock()
    with patch("app.services.catalog_service.Session") as session:
        session.return_value.__enter__.return_value.get.side_effect = OperationalError("private-sql", {}, Exception("private-password"))
        response = client.post("/v1/check", json={"hostname": "example.test"})
        assert response.status_code == 503
        assert "private" not in response.text
    connection = app.state.engine.connect.return_value.__enter__.return_value
    connection.execute.return_value.scalars.return_value.all.return_value = ["old_revision"]
    assert client.get("/health/ready").status_code == 503
    connection.execute.return_value.scalars.return_value.all.return_value = ["0001_catalog"]
    assert client.get("/health/ready").status_code == 200
