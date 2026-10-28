"""Interfaces des fournisseurs externes (e-mail, LinkedIn, CRM externe), dataclasses et exceptions."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Literal, Mapping, Protocol


class ErreurFournisseur(Exception):
    """Échec d'appel (transitoire ou non) : compte comme un essai. Jamais de clé dans le message."""


class SignatureInvalide(Exception):
    """Webhook refusé (401)."""


class CompteLinkedInDeconnecte(ErreurFournisseur):
    """Le compte LinkedIn doit être reconnecté."""


class NonConfigure(Exception):
    """Fournisseur absent ou incomplet dans la configuration."""


@dataclass
class MessageEmail:
    a: str
    sujet: str
    html: str
    texte: str
    expediteur: str                                       # "Nom <adresse>"
    repondre_a: str | None = None
    entetes: dict[str, str] = field(default_factory=dict)  # List-Unsubscribe, List-Unsubscribe-Post
    cle_idempotence: str | None = None
    etiquettes: dict[str, str] = field(default_factory=dict)  # inscription_id, pas


@dataclass
class EvenementEmail:
    cle: str                                              # svix-id
    type: Literal["delivre", "ouvert", "clique", "rebond", "plainte", "autre"]
    fournisseur_id: str
    recu_at: dt.datetime


class EmailProvider(Protocol):
    nom: str

    def envoyer(self, msg: MessageEmail) -> str:
        """Envoie le message et renvoie l'identifiant du fournisseur."""
        ...

    def analyser_webhook(self, entetes: Mapping[str, str], corps: bytes) -> list[EvenementEmail]: ...


@dataclass
class PersonneLinkedIn:
    provider_id: str
    prenom: str | None
    nom: str | None
    poste: str | None
    entreprise: str | None
    url: str | None


@dataclass
class ProfilLinkedIn(PersonneLinkedIn):
    posts_recents: list[tuple[dt.datetime, str]] = field(default_factory=list)  # 30 jours au plus


@dataclass
class EvenementLinkedIn:
    cle: str
    type: Literal["invitation_acceptee", "message_recu", "compte_deconnecte", "compte_ok", "autre"]
    provider_id: str | None
    texte: str | None
    recu_at: dt.datetime


class LinkedInProvider(Protocol):
    nom: str

    def etat_compte(self) -> Literal["ok", "a_reconnecter", "non_configure"]: ...
    def chercher(self, entreprise: str, postes: list[str], limite: int) -> list[PersonneLinkedIn]: ...
    def profil(self, provider_id: str) -> ProfilLinkedIn: ...
    def inviter(self, provider_id: str, note: str) -> str: ...
    def ecrire(self, provider_id: str, texte: str) -> str: ...
    def analyser_webhook(self, entetes: Mapping[str, str], corps: bytes) -> list[EvenementLinkedIn]: ...

    def verifier_acceptation(self, provider_id: str, url: str | None) -> bool | None:
        """Optionnelle, pour un fournisseur sans webhook d'acceptation : vrai si la relation est au
        1er degré, faux sinon, None si le fournisseur ne vérifie pas (il a le webhook) ou ne peut pas
        vérifier ce profil. Lève `ErreurFournisseur` en cas d'échec d'appel."""
        ...


# --------------------------------------------------------------------------- CRM externe (lot L8)

class LimiteDebit(ErreurFournisseur):
    """Limite de débit du CRM externe atteinte (429) : on arrête le passage, nouvel essai plus tard."""


class ObjetIntrouvable(ErreurFournisseur):
    """L'objet n'existe plus côté CRM externe (404 sur une mise à jour)."""


@dataclass(frozen=True)
class ProprieteCrm:
    """Propriété personnalisée à créer côté CRM externe si elle manque."""
    objet: Literal["contacts", "companies", "deals"]
    nom: str
    libelle: str
    type: str                        # string, enumeration, date
    champ: str                       # text, select, date
    options: tuple[tuple[str, str], ...] = ()    # (valeur, libellé)


class CrmExterneProvider(Protocol):
    """Réplication sens unique CRM MERCI vers un CRM externe. `objet` : contacts, companies, deals.
    Chaque méthode lève `ErreurFournisseur` (jamais de jeton dans le message)."""
    nom: str
    connecte: bool                   # faux : rien n'est envoyé, l'état local reste « à synchroniser »

    def assurer_proprietes(self, groupe: tuple[str, str], proprietes: list[ProprieteCrm]) -> None: ...
    def upsert_contact(self, email: str, proprietes: dict[str, str]) -> str: ...
    def creer(self, objet: str, proprietes: dict[str, str]) -> str: ...
    def modifier(self, objet: str, ident: str, proprietes: dict[str, str]) -> None: ...
    def associer(self, objet: str, ident: str, vers: str, vers_ident: str | None) -> None: ...

    def etapes_pipeline(self) -> list[dict[str, str]]:
        """Étapes du pipeline de deals par défaut, dans l'ordre : `[{id, label}]`."""
        ...
