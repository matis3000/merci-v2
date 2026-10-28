"""Déploiement Vercel (services) : le service reçoit le chemin public complet (`/api/...`).

Doc : https://vercel.com/docs/services/routing (« The service receives the original request path »).
L'API monte donc ses routes sous `PREFIXE_API` (`/api` sur Vercel, vide en local).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app import config as config_mod
from app.config import Settings, settings


def test_prefixe_vide_en_local(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("PREFIXE_API", raising=False)
    assert Settings(_env_file=None, mode="development").prefixe_api == ""


def test_prefixe_api_sur_vercel(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("PREFIXE_API", raising=False)
    monkeypatch.delenv("OUTBOX_DIR", raising=False)
    s = Settings(_env_file=None, mode="development")
    assert s.prefixe_api == "/api"
    assert s.outbox_dir == "/tmp/outbox"  # seul dossier inscriptible d'une fonction Vercel


def test_prefixe_explicite_prioritaire(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("PREFIXE_API", "")
    assert Settings(_env_file=None, mode="development").prefixe_api == ""


def test_routes_montees_sous_le_prefixe(engine, fournisseurs_factices, monkeypatch):
    monkeypatch.setattr(settings, "prefixe_api", "/api")
    from app.main import create_app

    with TestClient(create_app()) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/ready").json() == {"ok": True, "db": "up"}
        assert c.get("/health").status_code == 404
        r = c.post("/api/public/inscription", json={})
        assert r.status_code == 422  # la route existe sous /api, le corps vide est refusé
        assert c.post("/public/inscription", json={}).status_code == 404
    assert config_mod.settings is settings
