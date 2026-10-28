"""Tables SQLModel et énumérations du CRM MERCI (section 3 du dossier d'architecture).

Conventions : dates en UTC naïf produites par `temps.maintenant()` ; énumérations stockées en
texte et vérifiées par des `CHECK` ; JSON stocké en texte ; emails normalisés à l'écriture
(`strip().lower()`), ce qui rend l'unicité insensible à la casse sur SQLite comme sur Postgres.
La migration `0001_crm_merci` reproduit ce fichier à l'identique (`alembic check`).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import event
from sqlmodel import Field, SQLModel

# Énumérations
ROLES = ("admin", "equipe")
TYPES_ORGANISATION = ("entreprise", "association")
TYPES_CONTACT = ("donateur", "association", "entreprise")
SOURCES = ("landing", "prospection", "import", "manuel")
PIPELINES = ("donateurs", "entreprises", "associations")
TYPES_ACTIVITE = (
    "inscription", "reinscription", "import", "creation_manuelle", "prospection_trouve",
    "etape_changee", "sequence_inscrite", "sequence_arretee", "sequence_terminee", "sequence_echec",
    "email_envoye", "email_delivre", "email_ouvert", "email_clique", "email_rebond", "email_plainte",
    "linkedin_invitation", "linkedin_acceptee", "linkedin_message", "linkedin_reponse",
    "desinscription", "evenement_app", "note", "appel",
)
STATUTS_INSCRIPTION = ("active", "terminee", "arretee", "echec")
RAISONS_ARRET = (
    "reponse", "etape_changee", "perdu", "desinscription", "rebond", "plainte", "objectif_atteint",
    "sans_acceptation", "trois_essais", "envoi_incertain", "manuel",
)
CANAUX = ("email", "linkedin_invitation", "linkedin_message")
STATUTS_ENVOI = ("en_cours", "envoye", "erreur", "echec", "incertain", "saute")
FOURNISSEURS = ("resend", "console", "connectsafely", "factice")
ETATS_LINKEDIN = ("inconnu", "ok", "a_reconnecter", "non_configure")
DECLENCHEURS = ("cron", "manuel")
STATUTS_PASSAGE = ("en_cours", "fini", "erreur")


def _dans(table: str, colonne: str, valeurs: tuple[str, ...], nullable: bool = False) -> sa.CheckConstraint:
    liste = ", ".join(f"'{v}'" for v in valeurs)
    cond = f"{colonne} IN ({liste})"
    if nullable:
        cond = f"{colonne} IS NULL OR {cond}"
    return sa.CheckConstraint(cond, name=f"ck_{table}_{colonne}")


def normaliser_email(email: Optional[str]) -> Optional[str]:
    if email is None:
        return None
    return email.strip().lower() or None


class Membre(SQLModel, table=True):
    __tablename__ = "membre"
    __table_args__ = (
        sa.UniqueConstraint("email", name="uq_membre_email"),
        _dans("membre", "role", ROLES),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(max_length=254)
    prenom: str = Field(max_length=80)
    role: str = Field(max_length=10)
    actif: bool = True
    cree_at: dt.datetime
    derniere_connexion_at: Optional[dt.datetime] = None


class JetonConnexion(SQLModel, table=True):
    __tablename__ = "jeton_connexion"
    __table_args__ = (sa.UniqueConstraint("jeton_hash", name="uq_jeton_connexion_jeton_hash"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    jeton_hash: str = Field(max_length=80)
    email: str = Field(max_length=254, index=True)
    expire_at: dt.datetime
    utilise_at: Optional[dt.datetime] = None
    cree_at: dt.datetime


class Organisation(SQLModel, table=True):
    __tablename__ = "organisation"
    __table_args__ = (
        sa.UniqueConstraint("siren", name="uq_organisation_siren"),
        _dans("organisation", "type", TYPES_ORGANISATION),
        _dans("organisation", "source", SOURCES),
        sa.CheckConstraint("note IS NULL OR (note >= 0 AND note <= 10)", name="ck_organisation_note"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    type: str = Field(max_length=20)
    nom: str = Field(max_length=200, index=True)
    siren: Optional[str] = Field(default=None, max_length=9)
    ville: Optional[str] = Field(default=None, max_length=120)
    code_postal: Optional[str] = Field(default=None, max_length=5)
    departement: Optional[str] = Field(default=None, max_length=3, index=True)
    tranche_effectif: Optional[str] = Field(default=None, max_length=2)
    naf_code: Optional[str] = Field(default=None, max_length=6)
    naf_libelle: Optional[str] = Field(default=None, max_length=200)
    site_web: Optional[str] = Field(default=None, max_length=300)
    note: Optional[int] = None
    raisons_note: Optional[str] = Field(default=None, sa_type=sa.Text)  # JSON : liste de str
    signal_rse_at: Optional[dt.datetime] = None
    signal_rse_libelle: Optional[str] = Field(default=None, max_length=200)
    source: str = Field(max_length=20)
    recherche_linkedin_at: Optional[dt.datetime] = Field(default=None, index=True)
    cree_at: dt.datetime
    maj_at: dt.datetime


class Contact(SQLModel, table=True):
    __tablename__ = "contact"
    __table_args__ = (
        sa.UniqueConstraint("email", name="uq_contact_email"),
        sa.UniqueConstraint("linkedin_provider_id", name="uq_contact_linkedin_provider_id"),
        _dans("contact", "type", TYPES_CONTACT),
        _dans("contact", "source", SOURCES),
        sa.CheckConstraint(
            "email IS NOT NULL OR linkedin_provider_id IS NOT NULL OR prenom IS NOT NULL",
            name="ck_contact_identifiant",
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    type: str = Field(max_length=20)
    prenom: Optional[str] = Field(default=None, max_length=80)
    nom: Optional[str] = Field(default=None, max_length=80)
    email: Optional[str] = Field(default=None, max_length=254)
    telephone: Optional[str] = Field(default=None, max_length=30)
    linkedin_url: Optional[str] = Field(default=None, max_length=300)
    linkedin_provider_id: Optional[str] = Field(default=None, max_length=120)
    poste: Optional[str] = Field(default=None, max_length=200)
    ville: Optional[str] = Field(default=None, max_length=120)
    organisation_id: Optional[int] = Field(default=None, foreign_key="organisation.id",
                                           ondelete="SET NULL", index=True)
    source: str = Field(max_length=20, index=True)
    source_detail: Optional[str] = Field(default=None, max_length=80)
    consentement_at: Optional[dt.datetime] = None
    consentement_texte: Optional[str] = Field(default=None, max_length=500)
    desinscrit_at: Optional[dt.datetime] = None
    pause: bool = False
    cree_at: dt.datetime = Field(index=True)
    maj_at: dt.datetime


class Affaire(SQLModel, table=True):
    __tablename__ = "affaire"
    __table_args__ = (
        sa.UniqueConstraint("contact_id", "pipeline", name="uq_affaire_contact_pipeline"),
        sa.Index("ix_affaire_pipeline_etape", "pipeline", "etape"),
        _dans("affaire", "pipeline", PIPELINES),
        sa.CheckConstraint("contact_id IS NOT NULL OR organisation_id IS NOT NULL", name="ck_affaire_cible"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    pipeline: str = Field(max_length=20, index=True)
    etape: str = Field(max_length=40)
    etape_depuis: dt.datetime
    contact_id: Optional[int] = Field(default=None, foreign_key="contact.id", index=True)
    organisation_id: Optional[int] = Field(default=None, foreign_key="organisation.id", index=True)
    responsable_id: Optional[int] = Field(default=None, foreign_key="membre.id")
    montant_mensuel: Optional[Decimal] = Field(default=None, max_digits=10, decimal_places=2)
    perdue_raison: Optional[str] = Field(default=None, max_length=300)
    cree_at: dt.datetime
    maj_at: dt.datetime


class Activite(SQLModel, table=True):
    __tablename__ = "activite"
    __table_args__ = (
        sa.Index("ix_activite_contact_cree", "contact_id", "cree_at"),
        sa.Index("ix_activite_organisation_cree", "organisation_id", "cree_at"),
        _dans("activite", "type", TYPES_ACTIVITE),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    type: str = Field(max_length=40, index=True)
    titre: str = Field(max_length=200)
    texte: Optional[str] = Field(default=None, sa_type=sa.Text)
    contact_id: Optional[int] = Field(default=None, foreign_key="contact.id")
    organisation_id: Optional[int] = Field(default=None, foreign_key="organisation.id")
    affaire_id: Optional[int] = Field(default=None, foreign_key="affaire.id")
    envoi_id: Optional[int] = Field(default=None, foreign_key="envoi.id")
    membre_id: Optional[int] = Field(default=None, foreign_key="membre.id")
    donnees: Optional[str] = Field(default=None, sa_type=sa.Text)  # JSON
    cree_at: dt.datetime = Field(index=True)


class InscriptionSequence(SQLModel, table=True):
    __tablename__ = "inscription_sequence"
    __table_args__ = (
        sa.UniqueConstraint("contact_id", "sequence", name="uq_inscription_contact_sequence"),
        sa.Index("ix_inscription_statut_prochain", "statut", "prochain_envoi_at"),
        _dans("inscription_sequence", "statut", STATUTS_INSCRIPTION),
        _dans("inscription_sequence", "raison_arret", RAISONS_ARRET, nullable=True),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    contact_id: int = Field(foreign_key="contact.id", index=True)
    sequence: str = Field(max_length=40)
    pas_courant: int
    prochain_envoi_at: Optional[dt.datetime] = Field(default=None, index=True)
    ancre_at: dt.datetime
    statut: str = Field(max_length=20)
    raison_arret: Optional[str] = Field(default=None, max_length=60)
    inscrit_par_id: Optional[int] = Field(default=None, foreign_key="membre.id")
    cree_at: dt.datetime
    maj_at: dt.datetime


class Envoi(SQLModel, table=True):
    __tablename__ = "envoi"
    __table_args__ = (
        sa.UniqueConstraint("inscription_id", "pas", name="uq_envoi_inscription_pas"),
        _dans("envoi", "canal", CANAUX),
        _dans("envoi", "statut", STATUTS_ENVOI),
        _dans("envoi", "fournisseur", FOURNISSEURS, nullable=True),
        sa.CheckConstraint("essais >= 0 AND essais <= 3", name="ck_envoi_essais"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    inscription_id: int = Field(foreign_key="inscription_sequence.id")
    pas: int
    canal: str = Field(max_length=30)
    statut: str = Field(max_length=20)
    essais: int = 0
    derniere_erreur: Optional[str] = Field(default=None, max_length=500)
    fournisseur: Optional[str] = Field(default=None, max_length=30)
    fournisseur_id: Optional[str] = Field(default=None, max_length=120, index=True)
    envoye_at: Optional[dt.datetime] = Field(default=None, index=True)
    delivre_at: Optional[dt.datetime] = None
    ouvert_at: Optional[dt.datetime] = None
    clique_at: Optional[dt.datetime] = None
    accepte_at: Optional[dt.datetime] = None
    cree_at: dt.datetime
    maj_at: dt.datetime


class TextePas(SQLModel, table=True):
    __tablename__ = "texte_pas"
    __table_args__ = (sa.UniqueConstraint("sequence", "pas", name="uq_texte_pas_sequence_pas"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    sequence: str = Field(max_length=40)
    pas: int
    sujet: Optional[str] = Field(default=None, max_length=200)
    corps: str = Field(sa_type=sa.Text)
    maj_par_id: Optional[int] = Field(default=None, foreign_key="membre.id")
    maj_at: dt.datetime


class Reglage(SQLModel, table=True):
    """Une seule ligne (`id = 1`), créée par la migration avec les valeurs par défaut."""
    __tablename__ = "reglage"
    __table_args__ = (
        sa.CheckConstraint("id = 1", name="ck_reglage_ligne_unique"),
        _dans("reglage", "linkedin_etat", ETATS_LINKEDIN),
    )
    id: int = Field(default=1, primary_key=True)
    relances_en_pause: bool = False
    creneau_jours: str = Field(default="1,2,3,4,5", max_length=20)
    creneau_debut: int = 9
    creneau_fin: int = 18
    expediteur_nom: str = Field(default="", max_length=80)
    expediteur_email: str = Field(default="", max_length=254)
    reponse_a: Optional[str] = Field(default=None, max_length=254)
    lien_rdv: Optional[str] = Field(default=None, max_length=300)
    lien_creation_compte: Optional[str] = Field(default=None, max_length=300)
    pilote_ouvert_at: Optional[dt.datetime] = None
    sequences_coupees: str = Field(default="[]", sa_type=sa.Text)
    prospection_departements: str = Field(default='["67"]', sa_type=sa.Text)
    prospection_effectif_min: int = 50
    prospection_postes: str = Field(default='["DRH","RH","RSE","QVT","People"]', sa_type=sa.Text)
    prospection_plafond_jour: int = 20
    prospection_seuil: int = 6
    linkedin_etat: str = Field(default="inconnu", max_length=20)
    linkedin_etat_at: Optional[dt.datetime] = None
    hubspot_etapes: str = Field(default="{}", sa_type=sa.Text)  # JSON {pipeline: {étape: id d'étape HubSpot}}
    hubspot_proprietes_at: Optional[dt.datetime] = None          # propriétés MERCI créées dans HubSpot
    maj_at: dt.datetime


class PassageProspection(SQLModel, table=True):
    __tablename__ = "passage_prospection"
    __table_args__ = (
        sa.UniqueConstraint("cle", name="uq_passage_prospection_cle"),
        _dans("passage_prospection", "declencheur", DECLENCHEURS),
        _dans("passage_prospection", "statut", STATUTS_PASSAGE),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    cle: str = Field(max_length=60)
    declencheur: str = Field(max_length=10)
    statut: str = Field(max_length=10)
    debut_at: dt.datetime
    fin_at: Optional[dt.datetime] = None
    entreprises_vues: int = 0
    nouvelles: int = 0
    decideurs: int = 0
    en_sequence: int = 0
    erreur: Optional[str] = Field(default=None, max_length=500)


class Verrou(SQLModel, table=True):
    __tablename__ = "verrou"
    nom: str = Field(max_length=40, primary_key=True)
    jeton: str = Field(max_length=40)
    expire_at: dt.datetime


class WebhookRecu(SQLModel, table=True):
    __tablename__ = "webhook_recu"
    __table_args__ = (sa.UniqueConstraint("fournisseur", "cle", name="uq_webhook_recu_fournisseur_cle"),)
    id: Optional[int] = Field(default=None, primary_key=True)
    fournisseur: str = Field(max_length=30)
    cle: str = Field(max_length=120)
    recu_at: dt.datetime


OBJETS_SYNCHRO = ("contact", "organisation", "affaire")
ETATS_SYNCHRO = ("a_synchroniser", "ok", "erreur")


class SynchroHubspot(SQLModel, table=True):
    """Lot L8 : correspondance objet local et objet HubSpot, état de la réplication sens unique."""
    __tablename__ = "synchro_hubspot"
    __table_args__ = (
        sa.UniqueConstraint("objet_type", "objet_id", name="uq_synchro_hubspot_objet"),
        sa.Index("ix_synchro_hubspot_etat_prochain", "etat", "prochain_essai_at"),
        _dans("synchro_hubspot", "objet_type", OBJETS_SYNCHRO),
        _dans("synchro_hubspot", "etat", ETATS_SYNCHRO),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    objet_type: str = Field(max_length=20)
    objet_id: int
    hubspot_id: Optional[str] = Field(default=None, max_length=40)
    etat: str = Field(max_length=20)
    essais: int = 0
    derniere_erreur: Optional[str] = Field(default=None, max_length=500)  # jamais de jeton
    prochain_essai_at: Optional[dt.datetime] = None
    synchro_at: Optional[dt.datetime] = None      # dernière synchro réussie
    version: int = 1                              # +1 à chaque marquage : une modification pendant l'envoi n'est pas perdue
    cree_at: dt.datetime
    maj_at: dt.datetime


@event.listens_for(Membre, "before_insert")
@event.listens_for(Membre, "before_update")
@event.listens_for(JetonConnexion, "before_insert")
@event.listens_for(Contact, "before_insert")
@event.listens_for(Contact, "before_update")
def _normaliser_email(_mapper, _connexion, cible) -> None:
    cible.email = normaliser_email(cible.email)
