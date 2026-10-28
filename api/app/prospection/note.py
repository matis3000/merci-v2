"""Note /10 MERCI (section 7.2) : fonction pure, raisons lisibles.

Décideur RH ou RSE trouvé +4 ; 250 salariés et plus +3, 50 à 249 salariés +2 ; signal RSE de
moins de 30 jours +3 (post LinkedIn ou offre d'emploi). Maximum 10, minimum 0.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from typing import Protocol

TRANCHES_250_PLUS = ("32", "41", "42", "51", "52", "53")
TRANCHES_50_249 = ("21", "22", "31")
VALIDITE_SIGNAL = dt.timedelta(days=30)
# Mots-clés du signal RSE (décision D13), en minuscules sans accents ; liste courte et modifiable.
MOTS_RSE = ("rse", "qvt", "qvct", "responsabilite societale", "mecenat")


class OrganisationNotee(Protocol):
    tranche_effectif: str | None
    signal_rse_at: dt.datetime | None
    signal_rse_libelle: str | None


def normaliser(texte: str | None) -> str:
    """Minuscules, sans accents, espaces réduits."""
    if not texte:
        return ""
    sans = "".join(ch for ch in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(ch))
    return " ".join(sans.lower().split())


def _contient(texte: str, mot: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(mot)}(?!\w)", texte) is not None


def libelle_poste(intitule: str | None, postes: list[str]) -> str | None:
    """Premier poste de la cible présent dans l'intitulé (mot entier, sans accents), sinon None."""
    t = normaliser(intitule)
    return next((p for p in postes if normaliser(p) and _contient(t, normaliser(p))), None)


def texte_rse(texte: str | None) -> bool:
    t = normaliser(texte)
    return any(_contient(t, mot) for mot in MOTS_RSE)


def signal_valide(signal_at: dt.datetime | None, maintenant: dt.datetime) -> bool:
    return signal_at is not None and maintenant - signal_at < VALIDITE_SIGNAL


def _anciennete(jours: int) -> str:
    if jours <= 0:
        return "aujourd'hui"
    return f"il y a {jours} jour{'s' if jours > 1 else ''}"


def calculer(org: OrganisationNotee, poste_decideur: str | None, postes: list[str],
             maintenant: dt.datetime) -> tuple[int, list[str]]:
    """(note, raisons). `poste_decideur` : intitulé du décideur trouvé, None sinon."""
    note, raisons = 0, []
    libelle = libelle_poste(poste_decideur, postes) if poste_decideur else None
    if libelle:
        note += 4
        raisons.append(f"Décideur {libelle} trouvé +4")
    else:
        raisons.append("Aucun décideur RH ou RSE trouvé")
    if org.tranche_effectif in TRANCHES_250_PLUS:
        note += 3
        raisons.append("250 salariés et plus +3")
    elif org.tranche_effectif in TRANCHES_50_249:
        note += 2
        raisons.append("50 à 249 salariés +2")
    if signal_valide(org.signal_rse_at, maintenant):
        note += 3
        libelle_signal = org.signal_rse_libelle or "Post RSE"
        if libelle_signal.startswith("Post"):
            raisons.append(f"Post RSE {_anciennete((maintenant - org.signal_rse_at).days)} +3")
        else:
            raisons.append(f"{libelle_signal} ce mois +3")
    return max(0, min(10, note)), raisons
