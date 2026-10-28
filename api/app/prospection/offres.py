"""France Travail, API « Offres d'emploi » v2 : offres RSE ou QVT (signal de la note /10).

Porté au lot L1, branché au lot L5. Optionnel : sans FRANCE_TRAVAIL_CLIENT_ID et
FRANCE_TRAVAIL_CLIENT_SECRET, aucun appel.
- URL de base : https://api.francetravail.io/partenaire/offresdemploi
- Recherche : GET /v2/offres/search, paramètres `motsCles`, `departement` (5 au plus),
  `publieeDepuis` (jours), `range` (150 au plus par page). 204 = aucun résultat, 206 = partiel.
À confirmer sur l'espace francetravail.io avant activation : URL du jeton OAuth2
(client credentials), scope, valeurs admises de `publieeDepuis`.
"""
from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import settings

API_BASE = "https://api.francetravail.io/partenaire/offresdemploi"
TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"  # à confirmer
SCOPE = "api_offresdemploiv2 o2dsoffre"  # à confirmer
JOURS_ADMIS = (1, 3, 7, 14, 31)  # valeurs de publieeDepuis (à confirmer)
TIMEOUT = 20.0


class ErreurOffres(Exception):
    """Échec d'appel à France Travail (message sans secret)."""


@dataclass
class OffreRSE:
    entreprise: str
    intitule: str
    date: str  # AAAA-MM-JJ


def configure() -> bool:
    return bool(settings.france_travail_client_id and settings.france_travail_client_secret)


def _jeton(http: httpx.Client) -> str:
    r = http.post(TOKEN_URL, data={
        "grant_type": "client_credentials",
        "client_id": settings.france_travail_client_id,
        "client_secret": settings.france_travail_client_secret,
        "scope": SCOPE,
    })
    if r.status_code != 200 or "access_token" not in r.json():
        raise ErreurOffres(f"France Travail : authentification refusée (HTTP {r.status_code})")
    return r.json()["access_token"]


def chercher_offres(mots_cles: list[str], departements: list[str], jours: int = 31,
                    transport: httpx.BaseTransport | None = None) -> list[OffreRSE]:
    """Une recherche par mot-clé ; offres anonymes (sans entreprise) ignorées."""
    if not configure():
        return []
    publiee = min((j for j in JOURS_ADMIS if j >= max(1, jours)), default=31)
    offres: list[OffreRSE] = []
    with httpx.Client(timeout=TIMEOUT, transport=transport) as http:
        jeton = _jeton(http)
        for mot in mots_cles:
            params = {"motsCles": mot, "publieeDepuis": str(publiee), "range": "0-149"}
            if departements:
                params["departement"] = ",".join(departements[:5])
            r = http.get(f"{API_BASE}/v2/offres/search", params=params,
                         headers={"Authorization": f"Bearer {jeton}", "Accept": "application/json"})
            if r.status_code == 204:
                continue
            if r.status_code not in (200, 206):
                raise ErreurOffres(f"France Travail : recherche en échec (HTTP {r.status_code})")
            for o in r.json().get("resultats") or []:
                nom = ((o.get("entreprise") or {}).get("nom") or "").strip()
                if nom:
                    offres.append(OffreRSE(entreprise=nom, intitule=o.get("intitule") or "",
                                           date=(o.get("dateCreation") or "")[:10]))
    return offres
