"""Configuration de l'API, lue dans l'environnement et dans `.env`.

Mode « production » par défaut (fail-closed) : le mode développement doit être demandé
explicitement par `MODE=development`. En production, les secrets faibles ou par défaut,
les fournisseurs factices et les adresses non https sont refusés au démarrage.
"""
from __future__ import annotations

import os

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

FOURNISSEURS_LINKEDIN = ("factice", "connectsafely")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mode: str = "production"
    database_url: str = "sqlite:///./merci.db"
    # Production sans Resend ni LinkedIn (mise en ligne du pilote) : false. E-mails écrits dans la
    # boîte locale au lieu d'être envoyés, LinkedIn factice. Secrets, https et base restent exigés.
    exiger_fournisseurs: bool = True

    # Préfixe des routes : sur Vercel (services), l'API reçoit le chemin public complet `/api/...`
    # (https://vercel.com/docs/services/routing). Vide en local.
    prefixe_api: str = ""

    # Adresses
    web_url: str = "http://127.0.0.1:3000"
    api_url_publique: str = "http://127.0.0.1:8010"
    cors_origines: str = "http://127.0.0.1:5500,http://localhost:5500"
    trust_proxy: bool = False

    # Équipe
    admin_email: str = "valentin@merci.local"
    admin_prenom: str = "Valentin"

    # Secrets
    jwt_secret: str = "dev-jwt-secret-a-changer-en-production-000"
    session_jours: int = 7
    cron_secret: str = "dev-cron-secret"
    cle_app_merci: str = "dev-cle-app"

    # E-mails : clé vide = boîte locale outbox/
    resend_api_key: str = ""
    resend_webhook_secret: str = ""
    email_expediteur: str = "bonjour@exemple.test"
    email_expediteur_nom: str = "MERCI"
    outbox_dir: str = "outbox"

    # LinkedIn
    linkedin_fournisseur: str = "factice"
    linkedin_webhook_secret: str = ""
    connectsafely_api_key: str = ""
    connectsafely_account_id: str = ""

    # Offres d'emploi RSE (optionnel)
    france_travail_client_id: str = ""
    france_travail_client_secret: str = ""

    # HubSpot : jeton d'app privée ; vide = synchro factice (journal seulement)
    hubspot_token: str = ""

    @property
    def origines_cors(self) -> list[str]:
        return [o.strip() for o in self.cors_origines.split(",") if o.strip()]

    @model_validator(mode="after")
    def _verifier(self) -> "Settings":
        # Sur Vercel (VERCEL=1, posé dans les fonctions et par `vercel dev`) : routes sous /api et
        # boîte d'e-mails locale dans /tmp, seul dossier inscriptible. Une valeur explicite l'emporte.
        if os.environ.get("VERCEL"):
            if "prefixe_api" not in self.model_fields_set:
                self.prefixe_api = "/api"
            if "outbox_dir" not in self.model_fields_set:
                self.outbox_dir = "/tmp/outbox"
        if self.prefixe_api and not self.prefixe_api.startswith("/"):
            raise ValueError("PREFIXE_API doit commencer par /")
        self.prefixe_api = self.prefixe_api.rstrip("/")
        # Neon et Vercel donnent postgres:// ou postgresql:// ; le pilote installé est psycopg 3.
        for brut in ("postgres://", "postgresql://"):
            if self.database_url.startswith(brut):
                self.database_url = "postgresql+psycopg://" + self.database_url[len(brut):]
        if self.mode not in ("development", "production"):
            raise ValueError("MODE doit valoir development ou production")
        if self.linkedin_fournisseur not in FOURNISSEURS_LINKEDIN:
            raise ValueError("LINKEDIN_FOURNISSEUR doit valoir factice ou connectsafely")
        if self.mode == "production":
            erreurs = self._erreurs_production()
            if erreurs:
                raise ValueError("Configuration refusée en production : " + " ; ".join(erreurs))
        return self

    def _erreurs_production(self) -> list[str]:
        defauts = {nom: champ.default for nom, champ in type(self).model_fields.items()}
        e: list[str] = []
        if len(self.jwt_secret) < 32 or self.jwt_secret == defauts["jwt_secret"]:
            e.append("JWT_SECRET faible ou par défaut (32 caractères au moins)")
        for nom in ("cron_secret", "cle_app_merci"):
            if not getattr(self, nom) or getattr(self, nom) == defauts[nom]:
                e.append(f"{nom.upper()} vide ou par défaut")
        if self.exiger_fournisseurs:
            for nom in ("resend_api_key", "resend_webhook_secret", "linkedin_webhook_secret"):
                if not getattr(self, nom):
                    e.append(f"{nom.upper()} absent")
            if self.linkedin_fournisseur == "factice":
                e.append("LINKEDIN_FOURNISSEUR factice interdit")
        requis = (("connectsafely_api_key", "connectsafely_account_id")
                  if self.linkedin_fournisseur == "connectsafely" else ())
        e += [f"{nom.upper()} absent" for nom in requis if not getattr(self, nom)]
        if not self.admin_email or self.admin_email == defauts["admin_email"]:
            e.append("ADMIN_EMAIL absent ou par défaut")
        for nom in ("web_url", "api_url_publique"):
            if not getattr(self, nom).startswith("https://"):
                e.append(f"{nom.upper()} doit être en https")
        if self.database_url.startswith("sqlite"):
            e.append("DATABASE_URL SQLite interdit")
        return e


settings = Settings()
