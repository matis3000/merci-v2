"""Comparaison de secrets à temps constant, jeton de désinscription signé, limite de débit."""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
from collections import defaultdict, deque

from fastapi import Request

from . import temps
from .config import settings


def secrets_egaux(recu: str | None, attendu: str | None) -> bool:
    """Vrai si les deux valeurs sont identiques. Un secret non configuré refuse tout."""
    if not recu or not attendu:
        return False
    return hmac.compare_digest(recu.encode(), attendu.encode())


def _b64(octets: bytes) -> str:
    return base64.urlsafe_b64encode(octets).rstrip(b"=").decode()


def _signature(contact_id: int) -> str:
    mac = hmac.new(settings.jwt_secret.encode(), f"desinscription:{contact_id}".encode(), hashlib.sha256)
    return _b64(mac.digest())[:22]


def jeton_desinscription(contact_id: int) -> str:
    """`base64url(contact_id).base64url(HMAC-SHA256)[:22]`, sans expiration (section 4.10)."""
    return f"{_b64(str(contact_id).encode())}.{_signature(contact_id)}"


def lire_jeton_desinscription(jeton: str) -> int | None:
    """Identifiant du contact si le jeton est authentique, sinon None."""
    try:
        partie_id, signature = jeton.split(".", 1)
        contact_id = int(base64.urlsafe_b64decode(partie_id + "=" * (-len(partie_id) % 4)).decode())
    except (ValueError, UnicodeDecodeError):
        return None
    return contact_id if secrets_egaux(signature, _signature(contact_id)) else None


def ip_client(request: Request) -> str:
    """IP du client ; derrière le proxy de l'hébergeur (`TRUST_PROXY`), premier `X-Forwarded-For`."""
    if settings.trust_proxy:
        transmis = request.headers.get("x-forwarded-for", "")
        if transmis.strip():
            return transmis.split(",")[0].strip()
    return request.client.host if request.client else "inconnue"


class LimiteDebit:
    """Au plus `nombre` requêtes par clé sur une fenêtre glissante, en mémoire (décision D9)."""

    def __init__(self, nombre: int, fenetre: dt.timedelta):
        self.nombre = nombre
        self.fenetre = fenetre
        self._appels: dict[str, deque[dt.datetime]] = defaultdict(deque)
        _LIMITES.append(self)

    def autoriser(self, cle: str) -> bool:
        t = temps.maintenant()
        file = self._appels[cle]
        while file and file[0] <= t - self.fenetre:
            file.popleft()
        if len(file) >= self.nombre:
            return False
        file.append(t)
        return True

    def vider(self) -> None:
        self._appels.clear()


_LIMITES: list[LimiteDebit] = []


def reinitialiser_limites() -> None:
    for limite in _LIMITES:
        limite.vider()
