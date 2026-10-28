"""Session de l'équipe : jeton JWT dans le cookie `merci_session`, lien magique.

Dépendances FastAPI : `membre_connecte` (401 sans session valide ou membre inactif) et
`admin_requis` (403 hors rôle admin). Les dates viennent de `temps.maintenant()` : la
vérification d'expiration suit la même horloge que le reste de l'API.
"""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import secrets

import jwt
from fastapi import Depends, HTTPException, Request, Response
from sqlmodel import Session

from . import temps
from .config import settings
from .db import get_session
from .modeles import Membre

COOKIE_SESSION = "merci_session"
DUREE_LIEN = dt.timedelta(minutes=15)


def create_jwt(membre_id: int, email: str) -> str:
    expire = temps.maintenant() + dt.timedelta(days=settings.session_jours)
    payload = {"sub": str(membre_id), "email": email, "exp": calendar.timegm(expire.timetuple())}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def lire_jwt(jeton: str) -> int | None:
    """Identifiant du membre si le jeton est authentique et non expiré, sinon None."""
    try:
        payload = jwt.decode(jeton, settings.jwt_secret, algorithms=["HS256"],
                             options={"verify_exp": False, "require": ["exp", "sub"]})
        expire = dt.datetime.fromtimestamp(int(payload["exp"]), dt.timezone.utc).replace(tzinfo=None)
        membre_id = int(payload["sub"])
    except (jwt.PyJWTError, ValueError, TypeError):
        return None
    return membre_id if expire > temps.maintenant() else None


def poser_cookie(response: Response, jeton: str) -> None:
    response.set_cookie(
        COOKIE_SESSION, jeton,
        max_age=settings.session_jours * 86400,
        httponly=True, samesite="lax", path="/",
        secure=settings.mode == "production",
    )


def effacer_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_SESSION, path="/", httponly=True, samesite="lax",
                           secure=settings.mode == "production")


def new_magic_token() -> str:
    return secrets.token_urlsafe(32)


def hash_magic_token(token: str) -> str:
    """Valeur stockée en base pour un lien magique (le jeton brut n'est jamais stocké)."""
    return hashlib.sha256(token.strip().encode()).hexdigest()


def is_local_request(request: Request) -> bool:
    """Requête faite directement sur la machine (ni tunnel ni proxy).

    Les aides de développement (`dev_lien` renvoyé dans la réponse) ne sont jamais servies
    à une requête venue d'internet, même en MODE development.
    """
    if any(h in request.headers for h in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip", "forwarded")):
        return False
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost", "testclient")


def membre_connecte(request: Request, session: Session = Depends(get_session)) -> Membre:
    jeton = request.cookies.get(COOKIE_SESSION)
    membre_id = lire_jwt(jeton) if jeton else None
    membre = session.get(Membre, membre_id) if membre_id else None
    if membre is None or not membre.actif:
        raise HTTPException(401, "Session absente ou expirée, reconnectez-vous")
    return membre


def admin_requis(membre: Membre = Depends(membre_connecte)) -> Membre:
    if membre.role != "admin":
        raise HTTPException(403, "Action réservée à l'administrateur")
    return membre
