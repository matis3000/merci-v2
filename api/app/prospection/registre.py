"""API Recherche d'entreprises (data.gouv), gratuite et sans clé.

Porté au lot L1, branché au lot L5 (`moteur.py`).
Point d'accès : GET https://recherche-entreprises.api.gouv.fr/search
- `departement` : code(s) département (filtre les établissements), virgules
- `tranche_effectif_salarie` : code(s) de tranche INSEE, virgules
- `etat_administratif=A` (actives), `page`, `per_page` (25 au plus)
Réponse : `{results: [{siren, nom_complet, activite_principale, siege: {departement,
libelle_commune, code_postal, ...}, matching_etablissements: [...]}], total_pages, ...}`.
Limite publique : 7 requêtes par seconde ; en cas de 429, en-tête Retry-After.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

BASE_URL = "https://recherche-entreprises.api.gouv.fr/search"
PER_PAGE = 25
MIN_INTERVAL_S = 1 / 7      # 7 requêtes par seconde
MAX_RETRY_AFTER_S = 10.0

# (code tranche INSEE, borne basse, borne haute) ; NN et 00 exclus (sans salarié).
TRANCHES: list[tuple[str, int, int]] = [
    ("01", 1, 2), ("02", 3, 5), ("03", 6, 9), ("11", 10, 19), ("12", 20, 49),
    ("21", 50, 99), ("22", 100, 199), ("31", 200, 249), ("32", 250, 499),
    ("41", 500, 999), ("42", 1000, 1999), ("51", 2000, 4999), ("52", 5000, 9999),
    ("53", 10000, 10**9),
]


class ErreurRegistre(Exception):
    """Échec d'appel au registre (message sans donnée sensible)."""


@dataclass
class EntrepriseTrouvee:
    siren: str
    nom: str
    naf: str
    tranche: str
    ville: str
    code_postal: str
    departement: str


def tranches_depuis(effectif_min: int) -> list[str]:
    """Tranches INSEE dont la borne basse est au moins `effectif_min` (50 : 21 à 53)."""
    return [c for c, bas, _ in TRANCHES if bas >= effectif_min]


def _etablissement(res: dict, depts: list[str]) -> dict:
    """Établissement actif dans la zone demandée en priorité (le siège peut être ailleurs).
    Dictionnaire vide si aucun établissement actif dans la zone : hors cible."""
    siege = res.get("siege") or {}
    if depts:
        for m in res.get("matching_etablissements") or []:
            dep = m.get("departement") or (m.get("code_postal") or "")[:2]
            if m.get("etat_administratif", "A") == "A" and dep in depts:
                return {**m, "departement": dep}
        if siege.get("departement") not in depts:
            return {}
    return siege


class _Client:
    def __init__(self, http: httpx.Client, sleep) -> None:
        self.http, self.sleep, self.dernier = http, sleep, 0.0

    def get(self, params: dict) -> dict:
        for essai in range(2):
            attente = MIN_INTERVAL_S - (time.monotonic() - self.dernier)
            if attente > 0:
                self.sleep(attente)
            self.dernier = time.monotonic()
            try:
                r = self.http.get(BASE_URL, params=params)
            except httpx.HTTPError as e:
                raise ErreurRegistre(f"Registre : erreur réseau ({type(e).__name__})") from e
            if r.status_code == 429 and essai == 0:
                try:
                    delai = float(r.headers.get("Retry-After", "1"))
                except ValueError:
                    delai = 1.0
                self.sleep(min(max(delai, 0.0), MAX_RETRY_AFTER_S))
                continue
            if r.status_code != 200:
                raise ErreurRegistre(f"Registre : HTTP {r.status_code}")
            return r.json()
        raise ErreurRegistre("Registre : HTTP 429 persistant")


def chercher_entreprises(departements: list[str], tranches: list[str], pages_max: int,
                         transport: httpx.BaseTransport | None = None,
                         sleep=time.sleep) -> list[EntrepriseTrouvee]:
    """Entreprises actives ayant un établissement actif dans `departements`."""
    params = {"departement": ",".join(departements), "tranche_effectif_salarie": ",".join(tranches),
              "etat_administratif": "A", "per_page": PER_PAGE}
    trouvees: list[EntrepriseTrouvee] = []
    with httpx.Client(timeout=15.0, transport=transport) as http:
        client = _Client(http, sleep)
        for page in range(1, pages_max + 1):
            data = client.get({**params, "page": page})
            for res in data.get("results") or []:
                etab = _etablissement(res, departements)
                if not res.get("siren") or not etab:
                    continue
                trouvees.append(EntrepriseTrouvee(
                    siren=res["siren"],
                    nom=res.get("nom_complet") or res.get("nom_raison_sociale") or "",
                    naf=res.get("activite_principale") or "",
                    tranche=res.get("tranche_effectif_salarie") or "",
                    ville=(etab.get("libelle_commune") or "").title(),
                    code_postal=etab.get("code_postal") or "",
                    departement=etab.get("departement") or "",
                ))
            if page >= int(data.get("total_pages") or 1):
                break
    return trouvees
