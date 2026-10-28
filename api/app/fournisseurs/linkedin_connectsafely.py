"""LinkedInProvider ConnectSafely (section 6.3), appels HTTP en httpx.

Points d'accès confirmés sur la référence officielle ConnectSafely (consultée le 12/10/2026).
La page de synthèse https://connectsafely.ai/docs/api.html.md donne une autre base
(`https://connectsafely.ai/api`) et d'autres noms de champs : on suit la référence détaillée
de chaque point d'accès, plus récente et accompagnée d'exemples.
- Base `https://api.connectsafely.ai/linkedin`, en-tête `Authorization: Bearer <clé>`, `accountId`.
- chercher : `POST /search/people` `{accountId, keywords, count, filters: {company}}` ; réponse
  `people[]` (`profileUrn`, `firstName`, `lastName`, `headline`, `profileUrl`).
  https://connectsafely.ai/docs/api/linkedin-search/post-search-people-search-people
- profil : `POST /posts/latest` `{accountId, profileUrn, count (20 au plus), includeReposts}` ; réponse
  `posts[]` (`content`, `timestamp` relatif : « 3h », « 2d », « 1w », « 2mo »). La fiche profil
  (`POST /profile`) exige l'identifiant public et non l'URN : non utilisée, les nom et poste
  viennent de la recherche.
  https://connectsafely.ai/docs/api/linkedin-posts/post-posts-latest-get-latest-posts
- inviter : `POST /connect` `{accountId, profileUrn, customMessage (300 au plus)}` ; 90 par semaine.
  https://connectsafely.ai/docs/api/linkedin-actions/post-connect-send-connection-request
- ecrire : `POST /message` `{accountId, recipientProfileUrn, message, messageType: "normal"}` ;
  150 par jour. https://connectsafely.ai/docs/api/linkedin-actions/post-message-send-message
- etat_compte : `GET /account/{accountId}/status` ; `status` AVAILABLE, IN_USE ou ERROR, `enabled`,
  `hasTokens`. https://connectsafely.ai/docs/api/linkedin-account/get-account-accountid-status-get-account-status-by-id
- 401 : clé invalide, traité comme un compte à reconnecter (rien ne peut partir sans action).
- Webhooks : `X-Webhook-Signature: sha256=<hex>` (HMAC-SHA256 du corps brut avec le secret de
  signature), `X-Webhook-Timestamp` en secondes. https://connectsafely.ai/docs/webhooks/security
  Seul `message.received` existe (`data.message_urn`, `data.sender.id`, `data.body`).
  https://connectsafely.ai/docs/webhooks/events
  Aucun événement « invitation acceptée » n'est documenté : l'acceptation est détectée par le tick,
  qui vérifie la relation des invitations en attente (lot L5b, `verifier_acceptation`).
- verifier_acceptation : `GET /relationship/{accountId}/{profileId}`, `profileId` = identifiant public
  (la partie après linkedin.com/in/, pas l'URN) ; `status` CONNECTED (1er degré), INVITATION_SENT,
  INVITATION_RECEIVED (pas encore une relation) ou NOT_CONNECTED.
  https://connectsafely.ai/docs/api/linkedin-actions/get-relationship-accountid-profileid-check-relationship-specific-account
  (variante du compte par défaut : https://connectsafely.ai/docs/api/linkedin-actions/get-relationship-profileid-check-relationship)
"""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import hmac
import json
import re
import uuid
from typing import Any, Literal, Mapping
from urllib.parse import quote, unquote

import httpx

from .. import temps
from ..prospection.note import libelle_poste
from .base import (
    CompteLinkedInDeconnecte, ErreurFournisseur, EvenementLinkedIn, PersonneLinkedIn, ProfilLinkedIn,
    SignatureInvalide,
)
from .http_util import entete

BASE = "https://api.connectsafely.ai/linkedin"
TIMEOUT = 20.0
NOTE_MAX = 300
RESULTATS_PAR_RECHERCHE = 10
POSTS_LUS = 20
FENETRE_POSTS = dt.timedelta(days=30)
TOLERANCE_S = 5 * 60
_PROFIL_PUBLIC = re.compile(r"linkedin\.com/in/([^/?#]+)", re.I)
_RELATIF = re.compile(r"^\s*(\d+)\s*(mo|y|w|d|h|m|s)\b", re.I)
_DUREES = {"s": dt.timedelta(seconds=1), "m": dt.timedelta(minutes=1), "h": dt.timedelta(hours=1),
           "d": dt.timedelta(days=1), "w": dt.timedelta(weeks=1), "mo": dt.timedelta(days=30),
           "y": dt.timedelta(days=365)}


def date_relative(valeur: str | None, maintenant: dt.datetime) -> dt.datetime | None:
    """« 1w » : il y a une semaine. None si illisible."""
    m = _RELATIF.match(valeur or "")
    if not m:
        return None
    return maintenant - int(m.group(1)) * _DUREES[m.group(2).lower()]


class ConnectSafelyLinkedInProvider:
    nom = "connectsafely"

    def __init__(self, cle: str, compte: str, secret_webhook: str = "",
                 transport: httpx.BaseTransport | None = None):
        self._cle = cle
        self.compte = compte
        self._secret = secret_webhook
        self._transport = transport

    def _appel(self, methode: str, chemin: str, corps: dict | None = None) -> Any:
        try:
            with httpx.Client(timeout=TIMEOUT, transport=self._transport) as client:
                rep = client.request(methode, BASE + chemin, json=corps,
                                     headers={"Authorization": f"Bearer {self._cle}"})
        except httpx.HTTPError as exc:
            raise ErreurFournisseur(f"ConnectSafely : erreur réseau ({type(exc).__name__})") from None
        if rep.status_code in (401, 403):
            raise CompteLinkedInDeconnecte(f"ConnectSafely : HTTP {rep.status_code}")
        if not rep.is_success:
            raise ErreurFournisseur(f"ConnectSafely : HTTP {rep.status_code}")
        try:
            donnees = rep.json()
        except ValueError:
            raise ErreurFournisseur("ConnectSafely : réponse illisible") from None
        if isinstance(donnees, dict) and donnees.get("success") is False:
            raise ErreurFournisseur("ConnectSafely : demande refusée")
        return donnees

    def etat_compte(self) -> Literal["ok", "a_reconnecter", "non_configure"]:
        try:
            c = self._appel("GET", f"/account/{self.compte}/status")
        except CompteLinkedInDeconnecte:
            return "a_reconnecter"
        if c.get("status") == "ERROR" or c.get("enabled") is False or c.get("hasTokens") is False:
            return "a_reconnecter"
        return "ok"

    def chercher(self, entreprise: str, postes: list[str], limite: int) -> list[PersonneLinkedIn]:
        rep = self._appel("POST", "/search/people", {
            "accountId": self.compte, "keywords": " OR ".join(postes), "count": RESULTATS_PAR_RECHERCHE,
            "filters": {"company": entreprise}})
        personnes = []
        for p in rep.get("people") or []:
            if not isinstance(p, dict) or not p.get("profileUrn") or not libelle_poste(p.get("headline"), postes):
                continue
            personnes.append(PersonneLinkedIn(
                provider_id=str(p["profileUrn"]), prenom=p.get("firstName"), nom=p.get("lastName"),
                poste=p.get("headline"), entreprise=entreprise, url=p.get("profileUrl")))
            if len(personnes) >= limite:
                break
        return personnes

    def profil(self, provider_id: str) -> ProfilLinkedIn:
        rep = self._appel("POST", "/posts/latest", {"accountId": self.compte, "profileUrn": provider_id,
                                                    "count": POSTS_LUS, "includeReposts": False})
        t = temps.maintenant()
        recents = []
        for post in rep.get("posts") or []:
            quand = date_relative(post.get("timestamp"), t) if isinstance(post, dict) else None
            if quand is not None and t - quand < FENETRE_POSTS:
                recents.append((quand, post.get("content") or ""))
        return ProfilLinkedIn(provider_id=provider_id, prenom=None, nom=None, poste=None, entreprise=None,
                              url=None, posts_recents=recents)

    def inviter(self, provider_id: str, note: str) -> str:
        if len(note) > NOTE_MAX:
            raise ErreurFournisseur(f"Note d'invitation de plus de {NOTE_MAX} caractères")
        self._appel("POST", "/connect", {"accountId": self.compte, "profileUrn": provider_id, "customMessage": note})
        return f"connectsafely-{uuid.uuid4()}"  # la réponse documentée ne porte pas d'identifiant

    def ecrire(self, provider_id: str, texte: str) -> str:
        self._appel("POST", "/message", {"accountId": self.compte, "recipientProfileUrn": provider_id,
                                         "message": texte, "messageType": "normal"})
        return f"connectsafely-{uuid.uuid4()}"

    def verifier_acceptation(self, provider_id: str, url: str | None) -> bool | None:
        """Vrai si la relation est au 1er degré. None sans identifiant public lisible dans l'URL."""
        m = _PROFIL_PUBLIC.search(url or "")
        if not m:
            return None
        rep = self._appel("GET", f"/relationship/{quote(self.compte, safe='')}/{quote(unquote(m.group(1)), safe='')}")
        return isinstance(rep, dict) and rep.get("status") == "CONNECTED"

    def analyser_webhook(self, entetes: Mapping[str, str], corps: bytes) -> list[EvenementLinkedIn]:
        signature, horodatage = entete(entetes, "X-Webhook-Signature"), entete(entetes, "X-Webhook-Timestamp")
        if not (self._secret and signature and horodatage):
            raise SignatureInvalide("signature absente")
        attendue = "sha256=" + hmac.new(self._secret.encode(), corps, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature.encode(), attendue.encode()):
            raise SignatureInvalide("signature invalide")
        try:
            ecart = abs(calendar.timegm(temps.maintenant().timetuple()) - int(horodatage))
            d = json.loads(corps)
        except ValueError as exc:
            raise SignatureInvalide("corps illisible") from exc
        if ecart > TOLERANCE_S:
            raise SignatureInvalide("horodatage hors tolérance")
        if not isinstance(d, dict):
            raise SignatureInvalide("corps illisible")
        data = d.get("data")
        t = temps.maintenant()
        if (d.get("event") == "message.received" and isinstance(data, dict) and data.get("message_urn")
                and (data.get("sender") or {}).get("id") and data.get("account_id") in (None, self.compte)):
            return [EvenementLinkedIn(cle=str(data["message_urn"])[:120], type="message_recu",
                                      provider_id=str(data["sender"]["id"]), texte=data.get("body"), recu_at=t)]
        return [EvenementLinkedIn(cle=f"autre:{uuid.uuid4().hex}", type="autre", provider_id=None, texte=None,
                                  recu_at=t)]
