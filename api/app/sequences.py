"""Les 4 séquences de relance, définies en code (section 5.1).

Textes par défaut : ceux de la preview validée, complétés en messages entiers et signés par
Valentin ; l'équipe les modifie depuis l'écran Séquences (table `texte_pas`). Variables autorisées : {prenom}, {entreprise}, {lien_rdv},
{lien_compte}.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

VARIABLES = ("prenom", "entreprise", "lien_rdv", "lien_compte")
# Longueur maximale de chaque valeur (taille des colonnes) : sert au contrôle des 300 caractères
# d'une invitation LinkedIn avant l'envoi.
LONGUEUR_MAX = {"prenom": 80, "entreprise": 200, "lien_rdv": 300, "lien_compte": 300}
NOTE_INVITATION_MAX = 300
SIGNATURE = "\n\nValentin, de MERCI"
_VARIABLE = re.compile(r"\{(\w+)\}")


@dataclass(frozen=True)
class Pas:
    numero: int
    canal: Literal["email", "linkedin_invitation", "linkedin_message"]
    ancre: Literal["inscription", "acceptation"]   # point de départ du délai
    delai_jours: int
    titre: str                                      # libellé affiché dans l'app
    sujet: str | None                               # e-mail uniquement
    corps: str                                      # texte par défaut
    si: Literal["toujours", "email_connu", "linkedin_connu"] = "toujours"


@dataclass(frozen=True)
class Sequence:
    cle: str
    nom: str
    public: str
    declencheur: str
    types: tuple[str, ...]                          # types de contact compatibles
    pas: tuple[Pas, ...]
    succes_pas_1: tuple[str, str, str] | None       # (pipeline, depuis, vers) au premier envoi réussi
    expire_sans_acceptation_jours: int | None = None


SEQUENCES: dict[str, Sequence] = {s.cle: s for s in (
    Sequence(
        cle="donateur-bienvenue", nom="Bienvenue donateur", public="Donateurs",
        declencheur="Inscription sur la landing", types=("donateur",),
        pas=(
            Pas(1, "email", "inscription", 0, "Bienvenue chez MERCI", "Bienvenue chez MERCI",
                "Bonjour {prenom},\n\n"
                "Merci de rejoindre le pilote MERCI ! Vous faites partie des premières personnes à essayer une "
                "façon plus simple de donner : vous donnez quand vous le souhaitez, directement à l'association de "
                "votre choix, votre reçu fiscal arrive tout seul, et vous recevez des nouvelles du projet que vous "
                "avez aidé, jusqu'au merci.\n\n"
                "Le pilote ouvre en Alsace en 2027. Nous vous écrirons dès que votre compte sera prêt, pas avant.\n\n"
                "D'ici là, si une association près de chez vous mérite d'être connue, répondez à ce message : "
                "nous serons ravis de la rencontrer.\n\n"
                "À très vite,"
                + SIGNATURE),
        ),
        succes_pas_1=("donateurs", "inscrit", "bienvenue_envoyee"),
    ),
    Sequence(
        cle="donateur-pilote", nom="Ouverture du pilote", public="Donateurs",
        declencheur="Bouton « Ouvrir le pilote »", types=("donateur",),
        pas=(
            Pas(1, "email", "inscription", 0, "Le pilote est ouvert", "Le pilote est ouvert",
                "{prenom}, votre compte MERCI vous attend. Créez-le en deux minutes et retrouvez tous vos "
                "dons au même endroit : {lien_compte}" + SIGNATURE),
            Pas(2, "email", "inscription", 4, "Votre compte vous attend", "Votre compte vous attend",
                "Petit rappel : un seul compte pour donner, suivre vos dons et garder vos reçus.\n\n"
                "Créer mon compte : {lien_compte}" + SIGNATURE),
            Pas(3, "email", "inscription", 10, "Dernier rappel", "Dernier rappel",
                "On ne vous écrira plus à ce sujet. Le lien reste valable : {lien_compte}" + SIGNATURE),
        ),
        succes_pas_1=None,
    ),
    Sequence(
        cle="entreprise-entrante", nom="Entreprise entrante", public="Entreprises",
        declencheur="Case « entreprise » cochée", types=("entreprise",),
        pas=(
            Pas(1, "email", "inscription", 0, "Merci pour votre intérêt", "Merci pour votre intérêt, {prenom}",
                "Bonjour {prenom},\n\n"
                "Merci de vous intéresser à MERCI pour {entreprise}.\n\n"
                "Le principe est simple : chaque salarié reçoit un portefeuille générosité. Ceux qui le souhaitent "
                "y versent un petit don sur leur paie, l'entreprise ajoute sa part, et chacun choisit les "
                "associations et les projets qu'il veut soutenir, près de chez lui. Rien n'est prélevé sur les dons, "
                "et chaque année vous recevez le bilan de ce que vos équipes ont permis, utile pour votre démarche "
                "RSE.\n\n"
                "Le plus simple pour en parler : vingt minutes ensemble. Répondez à ce message avec deux ou trois "
                "créneaux qui vous arrangent, je m'adapte.\n\n"
                "Bien à vous,"
                + SIGNATURE),
            Pas(2, "email", "inscription", 3, "Un créneau cette semaine ?", "Un créneau cette semaine ?",
                "Bonjour {prenom},\n\n"
                "Je me permets de revenir vers vous au sujet du portefeuille générosité MERCI pour les salariés de "
                "{entreprise}. Auriez-vous vingt minutes cette semaine ou la suivante ? Un simple message avec le "
                "moment qui vous convient suffit.\n\n"
                "Bien à vous,"
                + SIGNATURE),
            Pas(3, "linkedin_invitation", "inscription", 7, "Invitation LinkedIn", None,
                "Bonjour {prenom}, vous avez demandé à découvrir MERCI pour vos salariés. Je serais ravi "
                "d'échanger avec vous ici. Valentin, de MERCI", si="linkedin_connu"),
        ),
        succes_pas_1=("entreprises", "prospect", "contacte"),
    ),
    Sequence(
        cle="association-bienvenue", nom="Bienvenue association", public="Associations",
        declencheur="Inscription sur la landing", types=("association",),
        pas=(
            Pas(1, "email", "inscription", 0, "Bienvenue dans le pilote", "Bienvenue dans le pilote, {entreprise}",
                "Bonjour {prenom},\n\n"
                "Merci d'avoir inscrit {entreprise} au pilote MERCI !\n\n"
                "Avec MERCI, vous recevez en entier, sans frais, les dons des particuliers comme ceux des salariés "
                "des entreprises partenaires, et les reçus fiscaux sont envoyés pour vous. Vous avez aussi une page pour présenter vos projets et donner des nouvelles à celles et ceux "
                "qui vous soutiennent.\n\n"
                "Le pilote ouvre en Alsace en 2027, avec un petit groupe d'associations fondatrices que nous "
                "accompagnons de près. Nous allons vous contacter dans les prochains jours pour faire connaissance. "
                "Si vous préférez choisir le moment, répondez simplement à ce message.\n\n"
                "À très vite,"
                + SIGNATURE),
        ),
        succes_pas_1=None,
    ),
    Sequence(
        cle="entreprise-prospection", nom="Prospection LinkedIn", public="Entreprises",
        declencheur="Prospect noté 6/10 ou plus", types=("entreprise",),
        pas=(
            Pas(1, "linkedin_invitation", "inscription", 0, "Invitation avec note", None,
                "Bonjour {prenom}, je prépare avec des entreprises d'Alsace un portefeuille générosité pour leurs "
                "salariés, au plus près des associations locales. Ravi d'échanger."),
            Pas(2, "linkedin_message", "acceptation", 0, "Message de présentation", None,
                "Merci d'avoir accepté, {prenom}. Avec MERCI, chaque salarié a un portefeuille générosité : il "
                "donne s'il le souhaite sur sa paie, l'entreprise ajoute sa part, et il choisit les associations "
                "d'Alsace qu'il soutient. Vous recevez chaque année un bilan utile à votre démarche RSE. "
                "Seriez-vous d'accord pour que je vous le présente en vingt minutes ?" + SIGNATURE),
            Pas(3, "linkedin_message", "acceptation", 4, "Relance", None,
                "Je reviens vers vous : une démo de vingt minutes la semaine prochaine ?"),
            Pas(4, "email", "acceptation", 9, "Relance par e-mail", "Une démo de MERCI pour vos salariés ?",
                "Bonjour {prenom},\n\nNous avons échangé sur LinkedIn il y a quelques jours. Avec MERCI, chacun de "
                "vos salariés a un portefeuille générosité pour soutenir les associations d'Alsace, et "
                "l'entreprise ajoute sa part.\n\n"
                "Auriez-vous vingt minutes pour une démo ? Répondez simplement avec deux ou trois créneaux qui "
                "vous arrangent." + SIGNATURE, si="email_connu"),
        ),
        succes_pas_1=("entreprises", "prospect", "contacte"),
        expire_sans_acceptation_jours=21,
    ),
)}


def delai_libelle(pas: Pas) -> str:
    """« J0 », « J+4 », « À l'acceptation », « +4 j après acceptation »."""
    if pas.ancre == "acceptation":
        return "À l'acceptation" if pas.delai_jours == 0 else f"+{pas.delai_jours} j après acceptation"
    return "J0" if pas.delai_jours == 0 else f"J+{pas.delai_jours}"


def canal_joignable(canal: str, email: str | None, linkedin_provider_id: str | None) -> bool:
    return bool(email) if canal == "email" else bool(linkedin_provider_id)


class VariableManquante(Exception):
    """Une variable du texte n'a pas de valeur : le pas ne part pas (pas de texte troué)."""


def variables_inconnues(texte: str) -> list[str]:
    return [v for v in _VARIABLE.findall(texte) if v not in VARIABLES]


def remplacer(texte: str, valeurs: dict[str, str | None]) -> str:
    def un(m: re.Match) -> str:
        nom = m.group(1)
        valeur = valeurs.get(nom)
        if not valeur:
            raise VariableManquante(f"Variable {{{nom}}} sans valeur : complétez la fiche ou les réglages")
        return valeur
    return _VARIABLE.sub(un, texte)


def longueur_max(texte: str) -> int:
    """Longueur une fois chaque variable remplacée par sa valeur la plus longue possible."""
    return len(_VARIABLE.sub(lambda m: "x" * LONGUEUR_MAX.get(m.group(1), 0), texte))
