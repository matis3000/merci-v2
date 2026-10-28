from __future__ import annotations

from sqlalchemy import create_engine

from app import db as db_mod


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "service": "crm-merci-api", "mode": "development"}


def test_ready_base_disponible(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "db": "up"}


def test_ready_base_indisponible_503_sans_detail(client, monkeypatch, tmp_path):
    introuvable = tmp_path / "absent" / "base.db"
    monkeypatch.setattr(db_mod, "engine", create_engine(f"sqlite:///{introuvable}"))
    r = client.get("/ready")
    assert r.status_code == 503
    assert r.json() == {"ok": False, "db": "down"}
