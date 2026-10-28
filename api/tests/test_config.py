from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings

PROD_VALIDE = dict(
    mode="production",
    database_url="postgresql+psycopg://u:p@hote/base",
    web_url="https://crm.exemple.test",
    api_url_publique="https://api.exemple.test",
    admin_email="admin@exemple.test",
    jwt_secret="x" * 40,
    cron_secret="cron-" + "y" * 30,
    cle_app_merci="app-" + "z" * 30,
    resend_api_key="cle-resend",
    resend_webhook_secret="whsec_test",
    linkedin_fournisseur="connectsafely",
    linkedin_webhook_secret="secret-li",
    connectsafely_api_key="cle-connectsafely",
    connectsafely_account_id="compte",
)


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_mode_production_par_defaut():
    assert Settings.model_fields["mode"].default == "production"


def test_development_accepte_les_valeurs_locales(monkeypatch):
    monkeypatch.delenv("ADMIN_EMAIL", raising=False)  # posée par conftest pour les autres tests
    s = _settings(mode="development")
    assert s.linkedin_fournisseur == "factice"
    assert s.admin_email == "valentin@merci.local"


def test_production_complete_acceptee():
    assert _settings(**PROD_VALIDE).mode == "production"


@pytest.mark.parametrize("champ,valeur", [
    ("jwt_secret", "court"),
    ("jwt_secret", Settings.model_fields["jwt_secret"].default),
    ("cron_secret", Settings.model_fields["cron_secret"].default),
    ("cle_app_merci", ""),
    ("resend_api_key", ""),
    ("resend_webhook_secret", ""),
    ("linkedin_fournisseur", "factice"),
    ("connectsafely_api_key", ""),
    ("connectsafely_account_id", ""),
    ("linkedin_webhook_secret", ""),
    ("admin_email", Settings.model_fields["admin_email"].default),
    ("web_url", "http://crm.exemple.test"),
    ("api_url_publique", "http://api.exemple.test"),
    ("database_url", "sqlite:///./merci.db"),
])
def test_production_refuse_une_configuration_faible(champ, valeur):
    with pytest.raises(ValidationError):
        _settings(**{**PROD_VALIDE, champ: valeur})
