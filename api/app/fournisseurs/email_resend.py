"""EmailProvider Resend : envoi par l'API HTTP, webhooks signés par Svix (section 6.3).

Envoi : `POST https://api.resend.com/emails`, en-tête `Idempotency-Key` (Resend ignore un second
envoi avec la même clé pendant 24 h ; la garantie principale reste la réservation en base).
Webhooks : signature Svix vérifiée en bibliothèque standard, horodatage à moins de 5 minutes.
"""
from __future__ import annotations

import base64
import binascii
import calendar
import hashlib
import hmac
import json
from typing import Mapping

import httpx

from .. import temps
from .base import ErreurFournisseur, EvenementEmail, MessageEmail, SignatureInvalide

URL_ENVOI = "https://api.resend.com/emails"
TOLERANCE_S = 5 * 60

TYPES_RESEND = {
    "email.delivered": "delivre",
    "email.opened": "ouvert",
    "email.clicked": "clique",
    "email.bounced": "rebond",
    "email.complained": "plainte",
}


def lire_evenement(cle: str, corps: bytes) -> EvenementEmail:
    """Événement Resend `{type, created_at, data: {email_id, ...}}` normalisé."""
    try:
        e = json.loads(corps)
        fournisseur_id = str(e["data"]["email_id"])
    except (ValueError, KeyError, TypeError) as exc:
        raise SignatureInvalide("corps illisible") from exc
    return EvenementEmail(cle=cle, type=TYPES_RESEND.get(e.get("type"), "autre"),
                          fournisseur_id=fournisseur_id, recu_at=temps.maintenant())


def verifier_svix(secret: str, entetes: Mapping[str, str], corps: bytes) -> str:
    """Renvoie le `svix-id` si la signature est valide, sinon lève `SignatureInvalide`."""
    ident, horodatage = entetes.get("svix-id"), entetes.get("svix-timestamp")
    signatures = entetes.get("svix-signature")
    if not (secret and ident and horodatage and signatures):
        raise SignatureInvalide("signature absente")
    try:
        ts = int(horodatage)
        cle = base64.b64decode(secret.removeprefix("whsec_"))
    except (ValueError, binascii.Error) as exc:
        raise SignatureInvalide("signature illisible") from exc
    if abs(calendar.timegm(temps.maintenant().timetuple()) - ts) > TOLERANCE_S:
        raise SignatureInvalide("horodatage hors tolérance")
    mac = hmac.new(cle, f"{ident}.{horodatage}.".encode() + corps, hashlib.sha256).digest()
    attendue = base64.b64encode(mac).decode()
    for partie in signatures.split():
        version, _, valeur = partie.partition(",")
        if version == "v1" and hmac.compare_digest(valeur, attendue):
            return ident
    raise SignatureInvalide("signature invalide")


class ResendEmailProvider:
    nom = "resend"

    def __init__(self, cle: str, secret_webhook: str = "", transport: httpx.BaseTransport | None = None):
        self._cle = cle
        self._secret = secret_webhook
        self._transport = transport

    def envoyer(self, msg: MessageEmail) -> str:
        corps = {
            "from": msg.expediteur, "to": [msg.a], "subject": msg.sujet, "html": msg.html, "text": msg.texte,
            "headers": msg.entetes, "tags": [{"name": k, "value": v} for k, v in msg.etiquettes.items()],
        }
        if msg.repondre_a:
            corps["reply_to"] = msg.repondre_a
        entetes = {"Authorization": f"Bearer {self._cle}"}
        if msg.cle_idempotence:
            entetes["Idempotency-Key"] = msg.cle_idempotence
        try:
            with httpx.Client(timeout=10, transport=self._transport) as client:
                rep = client.post(URL_ENVOI, json=corps, headers=entetes)
        except httpx.HTTPError as exc:
            raise ErreurFournisseur(f"Resend : erreur réseau ({type(exc).__name__})") from None
        if not rep.is_success:
            raise ErreurFournisseur(f"Resend : HTTP {rep.status_code}")
        try:
            return str(rep.json()["id"])
        except (ValueError, KeyError, TypeError):
            raise ErreurFournisseur("Resend : réponse illisible") from None

    def analyser_webhook(self, entetes: Mapping[str, str], corps: bytes) -> list[EvenementEmail]:
        return [lire_evenement(verifier_svix(self._secret, entetes, corps), corps)]
