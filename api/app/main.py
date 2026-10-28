"""Application FastAPI du CRM MERCI."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from . import db, temps
from .config import settings
from .modeles import Membre, Reglage, normaliser_email
from .routes import accueil as routes_accueil
from .routes import auth as routes_auth
from .routes import contacts as routes_contacts
from .routes import coque as routes_coque
from .routes import cron as routes_cron
from .routes import hubspot as routes_hubspot
from .routes import pipelines as routes_pipelines
from .routes import prospection as routes_prospection
from .routes import public as routes_public
from .routes import reglages as routes_reglages
from .routes import sequences as routes_sequences
from .routes import webhooks as routes_webhooks

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("merci")


def initialiser(session: Session) -> None:
    """Au démarrage, sans rien inventer : admin du pilote depuis ADMIN_EMAIL (création
    idempotente) et expéditeur copié depuis l'environnement si la migration l'a laissé vide."""
    t = temps.maintenant()
    email = normaliser_email(settings.admin_email)
    if email and session.exec(select(Membre).where(Membre.email == email)).first() is None:
        session.add(Membre(email=email, prenom=settings.admin_prenom, role="admin", actif=True, cree_at=t))
        log.info("admin du pilote créé")
    reglage = session.get(Reglage, 1)
    if reglage is not None and not reglage.expediteur_email:
        reglage.expediteur_nom = reglage.expediteur_nom or settings.email_expediteur_nom
        reglage.expediteur_email = settings.email_expediteur
        reglage.maj_at = t
        session.add(reglage)
    session.commit()


@asynccontextmanager
async def _cycle(app: FastAPI):
    try:
        with Session(db.engine) as session:
            initialiser(session)
    except OperationalError:
        log.error("base non migrée : lancez `alembic upgrade head` puis redémarrez")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="CRM MERCI", version="0.1.0", lifespan=_cycle)
    # Une seule règle CORS (section 9.4) : seule la landing appelle l'API depuis une autre origine.
    # Le CRM web passe par la réécriture Next (même origine).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origines_cors,
        allow_methods=["POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        allow_credentials=False,
    )
    # Routeurs qui écrivent des contacts, organisations ou affaires : envoi HubSpot après la réponse.
    ecrivent = (routes_pipelines, routes_contacts, routes_sequences, routes_prospection, routes_public, routes_webhooks)
    racine = settings.prefixe_api  # "/api" sur Vercel, "" en local (voir config.py)
    for module in (routes_auth, routes_coque, routes_accueil, routes_pipelines, routes_contacts, routes_reglages,
                   routes_sequences, routes_prospection, routes_public, routes_cron, routes_webhooks, routes_hubspot):
        dependances = [Depends(routes_hubspot.planifier_envoi)] if module in ecrivent else []
        app.include_router(module.router, prefix=racine, dependencies=dependances)

    @app.get(f"{racine}/health")
    def health():
        return {"ok": True, "service": "crm-merci-api", "mode": settings.mode}

    @app.get(f"{racine}/ready")
    def ready():
        try:
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            log.exception("base indisponible")
            return JSONResponse({"ok": False, "db": "down"}, status_code=503)
        return {"ok": True, "db": "up"}

    return app


app = create_app()
