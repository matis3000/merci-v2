"""Les 3 pipelines, leurs étapes, et leur rattachement au parcours (section 3.3).

Les étapes sont stockées par clé ; les libellés sont servis par l'API (décision D3).
"""
from __future__ import annotations

PIPELINES: dict[str, dict] = {
    "donateurs": {
        "nom": "Donateurs",
        "etapes": [
            ("inscrit", "Inscrit"),
            ("bienvenue_envoyee", "Bienvenue envoyée"),
            ("pilote_ouvert", "Pilote ouvert"),
            ("compte_cree", "Compte créé"),
            ("premier_don", "Premier don"),
            ("fidele", "Fidèle"),
        ],
        "perdue": ("perdu", "Perdu"),
    },
    "entreprises": {
        "nom": "Entreprises",
        "etapes": [
            ("prospect", "Prospect"),
            ("contacte", "Contacté"),
            ("a_repondu", "A répondu"),
            ("demo_planifiee", "Démo planifiée"),
            ("demo_faite", "Démo faite"),
            ("abonnement_signe", "Abonnement signé"),
            ("salaries_actives", "Salariés activés"),
        ],
        "perdue": ("perdu", "Perdu"),
    },
    "associations": {
        "nom": "Associations",
        "etapes": [
            ("inscrite", "Inscrite"),
            ("contactee", "Contactée"),
            ("partenaire", "Partenaire"),
        ],
        "perdue": ("perdue", "Perdue"),
    },
}

# Étape du parcours de chaque étape de pipeline (repris de la preview, fait foi pour l'accueil).
# Les étapes perdues ne sont rattachées à rien ; le pipeline Associations n'est pas sur la grille.
RATTACHE: dict[str, dict[str, str]] = {
    "donateurs": {
        "inscrit": "capturer",
        "bienvenue_envoyee": "suivre",
        "pilote_ouvert": "relancer",
        "compte_cree": "convertir",
        "premier_don": "convertir",
        "fidele": "fideliser",
    },
    "entreprises": {
        "prospect": "capturer",
        "a_repondu": "suivre",
        "contacte": "relancer",
        "demo_planifiee": "convertir",
        "demo_faite": "convertir",
        "abonnement_signe": "convertir",
        "salaries_actives": "fideliser",
    },
}

ETAPES_PARCOURS = [
    {"cle": "attirer", "nom": "Attirer", "info": "D'où ils viennent"},
    {"cle": "capturer", "nom": "Capturer", "info": "Inscrits, prospects"},
    {"cle": "suivre", "nom": "Suivre", "info": "Qualifier"},
    {"cle": "relancer", "nom": "Relancer", "info": "Séquences en cours"},
    {"cle": "convertir", "nom": "Convertir", "info": "Compte, démo, signature"},
    {"cle": "fideliser", "nom": "Fidéliser", "info": "Dons, salariés actifs"},
]


def cles_etapes(pipeline: str) -> list[str]:
    """Clés dans l'ordre, étape perdue en dernier."""
    p = PIPELINES[pipeline]
    return [cle for cle, _ in p["etapes"]] + [p["perdue"][0]]


def etape_perdue(pipeline: str) -> str:
    return PIPELINES[pipeline]["perdue"][0]


def etape(pipeline: str, cle: str) -> dict[str, str]:
    p = PIPELINES[pipeline]
    for c, nom in p["etapes"] + [p["perdue"]]:
        if c == cle:
            return {"cle": c, "nom": nom}
    raise KeyError(f"étape inconnue : {pipeline}/{cle}")


def definition(pipeline: str) -> dict:
    """Forme `PipelineDef` du contrat d'API."""
    p = PIPELINES[pipeline]
    return {
        "cle": pipeline,
        "nom": p["nom"],
        "etapes": [{"cle": c, "nom": n} for c, n in p["etapes"]],
        "etape_perdue": {"cle": p["perdue"][0], "nom": p["perdue"][1]},
    }


def avance(pipeline: str, actuelle: str, cible: str) -> bool:
    """Vrai si un changement automatique de `actuelle` vers `cible` est permis.

    Une étape ne recule jamais automatiquement (invariant 8) ; une affaire perdue n'est plus
    déplacée automatiquement, et le passage en perdu reste une décision de l'équipe.
    """
    perdue = etape_perdue(pipeline)
    if perdue in (actuelle, cible):
        return False
    ordre = cles_etapes(pipeline)
    return ordre.index(cible) > ordre.index(actuelle)
