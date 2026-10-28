"""Mise en ligne avant Resend et LinkedIn : `EXIGER_FOURNISSEURS=false`.

La production reste stricte sur les secrets, le https et la base. Seuls Resend et LinkedIn
deviennent facultatifs : e-mails écrits dans la boîte locale (non envoyés), LinkedIn factice.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app import fournisseurs
from app.config import Settings, settings
from app.fournisseurs.email_console import ConsoleEmailProvider
from app.fournisseurs.linkedin_factice import FauxLinkedInProvider

LANCEMENT = dict(
    mode="production",
    exiger_fournisseurs=False,
    database_url="postgresql+psycopg://u:p@hote/base",
    web_url="https://crm.exemple.test",
    api_url_publique="https://exemple.test/api",
    admin_email="admin@exemple.test",
    jwt_secret="x" * 40,
    cron_secret="cron-" + "y" * 30,
    cle_app_merci="app-" + "z" * 30,
)


def _s(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_exigence_par_defaut():
    assert Settings.model_fields["exiger_fournisseurs"].default is True
    with pytest.raises(ValidationError):
        _s(**{**LANCEMENT, "exiger_fournisseurs": True})


def test_lancement_sans_resend_ni_linkedin_accepte():
    assert _s(**LANCEMENT).mode == "production"


@pytest.mark.parametrize("champ,valeur", [
    ("jwt_secret", "court"),
    ("cron_secret", Settings.model_fields["cron_secret"].default),
    ("cle_app_merci", ""),
    ("admin_email", Settings.model_fields["admin_email"].default),
    ("web_url", "http://crm.exemple.test"),
    ("database_url", "sqlite:///./merci.db"),
])
def test_lancement_reste_strict_sur_le_reste(champ, valeur):
    with pytest.raises(ValidationError):
        _s(**{**LANCEMENT, champ: valeur})


@pytest.mark.parametrize("brute", [
    "postgres://u:p@hote/base?sslmode=require",
    "postgresql://u:p@hote/base?sslmode=require",
])
def test_url_postgres_passe_par_psycopg(brute):
    assert _s(**{**LANCEMENT, "database_url": brute}).database_url == "postgresql+psycopg://u:p@hote/base?sslmode=require"


def test_fournisseurs_factices_acceptes_au_lancement(monkeypatch):
    monkeypatch.setattr(settings, "mode", "production")
    monkeypatch.setattr(settings, "resend_api_key", "")
    monkeypatch.setattr(settings, "linkedin_fournisseur", "factice")
    monkeypatch.setattr(settings, "exiger_fournisseurs", False)
    assert isinstance(fournisseurs.get_email_provider(), ConsoleEmailProvider)
    assert isinstance(fournisseurs.get_linkedin_provider(), FauxLinkedInProvider)
