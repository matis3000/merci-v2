"""CRM MERCI : schéma initial (section 3 du dossier d'architecture).

Crée les 13 tables avec index, contraintes uniques, CHECK et clés étrangères, puis insère la
ligne unique `reglage` (id = 1) avec ses valeurs par défaut. Aucune autre donnée.
Les valeurs d'expéditeur restent vides : l'API les copie depuis l'environnement au démarrage.

Revision ID: 0001
Revises:
Create Date: 2026-10-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import temps

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _s(n: int) -> sa.String:
    return sa.String(length=n)


def _dans(table: str, colonne: str, valeurs: tuple[str, ...], nullable: bool = False) -> sa.CheckConstraint:
    cond = f"{colonne} IN ({', '.join(repr(v) for v in valeurs)})"
    if nullable:
        cond = f"{colonne} IS NULL OR {cond}"
    return sa.CheckConstraint(cond, name=f"ck_{table}_{colonne}")


def _id() -> sa.Column:
    return sa.Column("id", sa.Integer(), primary_key=True)


def _date(nom: str, nullable: bool = False) -> sa.Column:
    return sa.Column(nom, sa.DateTime(), nullable=nullable)


SOURCES = ("landing", "prospection", "import", "manuel")
TYPES_ACTIVITE = (
    "inscription", "reinscription", "import", "creation_manuelle", "prospection_trouve",
    "etape_changee", "sequence_inscrite", "sequence_arretee", "sequence_terminee", "sequence_echec",
    "email_envoye", "email_delivre", "email_ouvert", "email_clique", "email_rebond", "email_plainte",
    "linkedin_invitation", "linkedin_acceptee", "linkedin_message", "linkedin_reponse",
    "desinscription", "evenement_app", "note", "appel",
)
RAISONS_ARRET = (
    "reponse", "etape_changee", "perdu", "desinscription", "rebond", "plainte", "objectif_atteint",
    "sans_acceptation", "trois_essais", "envoi_incertain", "manuel",
)

TABLES = (
    "membre", "jeton_connexion", "organisation", "contact", "affaire", "inscription_sequence",
    "envoi", "activite", "texte_pas", "reglage", "passage_prospection", "verrou", "webhook_recu",
)


def upgrade() -> None:
    op.create_table(
        "membre",
        _id(),
        sa.Column("email", _s(254), nullable=False),
        sa.Column("prenom", _s(80), nullable=False),
        sa.Column("role", _s(10), nullable=False),
        sa.Column("actif", sa.Boolean(), nullable=False),
        _date("cree_at"),
        _date("derniere_connexion_at", nullable=True),
        sa.UniqueConstraint("email", name="uq_membre_email"),
        _dans("membre", "role", ("admin", "equipe")),
    )

    op.create_table(
        "jeton_connexion",
        _id(),
        sa.Column("jeton_hash", _s(80), nullable=False),
        sa.Column("email", _s(254), nullable=False),
        _date("expire_at"),
        _date("utilise_at", nullable=True),
        _date("cree_at"),
        sa.UniqueConstraint("jeton_hash", name="uq_jeton_connexion_jeton_hash"),
    )
    op.create_index("ix_jeton_connexion_email", "jeton_connexion", ["email"])

    op.create_table(
        "organisation",
        _id(),
        sa.Column("type", _s(20), nullable=False),
        sa.Column("nom", _s(200), nullable=False),
        sa.Column("siren", _s(9), nullable=True),
        sa.Column("ville", _s(120), nullable=True),
        sa.Column("code_postal", _s(5), nullable=True),
        sa.Column("departement", _s(3), nullable=True),
        sa.Column("tranche_effectif", _s(2), nullable=True),
        sa.Column("naf_code", _s(6), nullable=True),
        sa.Column("naf_libelle", _s(200), nullable=True),
        sa.Column("site_web", _s(300), nullable=True),
        sa.Column("note", sa.Integer(), nullable=True),
        sa.Column("raisons_note", sa.Text(), nullable=True),
        _date("signal_rse_at", nullable=True),
        sa.Column("signal_rse_libelle", _s(200), nullable=True),
        sa.Column("source", _s(20), nullable=False),
        _date("recherche_linkedin_at", nullable=True),
        _date("cree_at"),
        _date("maj_at"),
        sa.UniqueConstraint("siren", name="uq_organisation_siren"),
        _dans("organisation", "type", ("entreprise", "association")),
        _dans("organisation", "source", SOURCES),
        sa.CheckConstraint("note IS NULL OR (note >= 0 AND note <= 10)", name="ck_organisation_note"),
    )
    op.create_index("ix_organisation_nom", "organisation", ["nom"])
    op.create_index("ix_organisation_departement", "organisation", ["departement"])
    op.create_index("ix_organisation_recherche_linkedin_at", "organisation", ["recherche_linkedin_at"])

    op.create_table(
        "contact",
        _id(),
        sa.Column("type", _s(20), nullable=False),
        sa.Column("prenom", _s(80), nullable=True),
        sa.Column("nom", _s(80), nullable=True),
        sa.Column("email", _s(254), nullable=True),
        sa.Column("telephone", _s(30), nullable=True),
        sa.Column("linkedin_url", _s(300), nullable=True),
        sa.Column("linkedin_provider_id", _s(120), nullable=True),
        sa.Column("poste", _s(200), nullable=True),
        sa.Column("ville", _s(120), nullable=True),
        sa.Column("organisation_id", sa.Integer(),
                  sa.ForeignKey("organisation.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", _s(20), nullable=False),
        sa.Column("source_detail", _s(80), nullable=True),
        _date("consentement_at", nullable=True),
        sa.Column("consentement_texte", _s(500), nullable=True),
        _date("desinscrit_at", nullable=True),
        sa.Column("pause", sa.Boolean(), nullable=False),
        _date("cree_at"),
        _date("maj_at"),
        sa.UniqueConstraint("email", name="uq_contact_email"),
        sa.UniqueConstraint("linkedin_provider_id", name="uq_contact_linkedin_provider_id"),
        _dans("contact", "type", ("donateur", "association", "entreprise")),
        _dans("contact", "source", SOURCES),
        sa.CheckConstraint("email IS NOT NULL OR linkedin_provider_id IS NOT NULL OR prenom IS NOT NULL",
                           name="ck_contact_identifiant"),
    )
    op.create_index("ix_contact_organisation_id", "contact", ["organisation_id"])
    op.create_index("ix_contact_source", "contact", ["source"])
    op.create_index("ix_contact_cree_at", "contact", ["cree_at"])

    op.create_table(
        "affaire",
        _id(),
        sa.Column("pipeline", _s(20), nullable=False),
        sa.Column("etape", _s(40), nullable=False),
        _date("etape_depuis"),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contact.id"), nullable=True),
        sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisation.id"), nullable=True),
        sa.Column("responsable_id", sa.Integer(), sa.ForeignKey("membre.id"), nullable=True),
        sa.Column("montant_mensuel", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("perdue_raison", _s(300), nullable=True),
        _date("cree_at"),
        _date("maj_at"),
        sa.UniqueConstraint("contact_id", "pipeline", name="uq_affaire_contact_pipeline"),
        _dans("affaire", "pipeline", ("donateurs", "entreprises", "associations")),
        sa.CheckConstraint("contact_id IS NOT NULL OR organisation_id IS NOT NULL", name="ck_affaire_cible"),
    )
    op.create_index("ix_affaire_pipeline", "affaire", ["pipeline"])
    op.create_index("ix_affaire_pipeline_etape", "affaire", ["pipeline", "etape"])
    op.create_index("ix_affaire_contact_id", "affaire", ["contact_id"])
    op.create_index("ix_affaire_organisation_id", "affaire", ["organisation_id"])

    op.create_table(
        "inscription_sequence",
        _id(),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contact.id"), nullable=False),
        sa.Column("sequence", _s(40), nullable=False),
        sa.Column("pas_courant", sa.Integer(), nullable=False),
        _date("prochain_envoi_at", nullable=True),
        _date("ancre_at"),
        sa.Column("statut", _s(20), nullable=False),
        sa.Column("raison_arret", _s(60), nullable=True),
        sa.Column("inscrit_par_id", sa.Integer(), sa.ForeignKey("membre.id"), nullable=True),
        _date("cree_at"),
        _date("maj_at"),
        sa.UniqueConstraint("contact_id", "sequence", name="uq_inscription_contact_sequence"),
        _dans("inscription_sequence", "statut", ("active", "terminee", "arretee", "echec")),
        _dans("inscription_sequence", "raison_arret", RAISONS_ARRET, nullable=True),
    )
    op.create_index("ix_inscription_sequence_contact_id", "inscription_sequence", ["contact_id"])
    op.create_index("ix_inscription_sequence_prochain_envoi_at", "inscription_sequence", ["prochain_envoi_at"])
    op.create_index("ix_inscription_statut_prochain", "inscription_sequence", ["statut", "prochain_envoi_at"])

    op.create_table(
        "envoi",
        _id(),
        sa.Column("inscription_id", sa.Integer(), sa.ForeignKey("inscription_sequence.id"), nullable=False),
        sa.Column("pas", sa.Integer(), nullable=False),
        sa.Column("canal", _s(30), nullable=False),
        sa.Column("statut", _s(20), nullable=False),
        sa.Column("essais", sa.Integer(), nullable=False),
        sa.Column("derniere_erreur", _s(500), nullable=True),
        sa.Column("fournisseur", _s(30), nullable=True),
        sa.Column("fournisseur_id", _s(120), nullable=True),
        _date("envoye_at", nullable=True),
        _date("delivre_at", nullable=True),
        _date("ouvert_at", nullable=True),
        _date("clique_at", nullable=True),
        _date("accepte_at", nullable=True),
        _date("cree_at"),
        _date("maj_at"),
        sa.UniqueConstraint("inscription_id", "pas", name="uq_envoi_inscription_pas"),
        _dans("envoi", "canal", ("email", "linkedin_invitation", "linkedin_message")),
        _dans("envoi", "statut", ("en_cours", "envoye", "erreur", "echec", "incertain", "saute")),
        _dans("envoi", "fournisseur", ("resend", "console", "connectsafely", "factice"), nullable=True),
        sa.CheckConstraint("essais >= 0 AND essais <= 3", name="ck_envoi_essais"),
    )
    op.create_index("ix_envoi_fournisseur_id", "envoi", ["fournisseur_id"])
    op.create_index("ix_envoi_envoye_at", "envoi", ["envoye_at"])

    op.create_table(
        "activite",
        _id(),
        sa.Column("type", _s(40), nullable=False),
        sa.Column("titre", _s(200), nullable=False),
        sa.Column("texte", sa.Text(), nullable=True),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contact.id"), nullable=True),
        sa.Column("organisation_id", sa.Integer(), sa.ForeignKey("organisation.id"), nullable=True),
        sa.Column("affaire_id", sa.Integer(), sa.ForeignKey("affaire.id"), nullable=True),
        sa.Column("envoi_id", sa.Integer(), sa.ForeignKey("envoi.id"), nullable=True),
        sa.Column("membre_id", sa.Integer(), sa.ForeignKey("membre.id"), nullable=True),
        sa.Column("donnees", sa.Text(), nullable=True),
        _date("cree_at"),
        _dans("activite", "type", TYPES_ACTIVITE),
    )
    op.create_index("ix_activite_type", "activite", ["type"])
    op.create_index("ix_activite_cree_at", "activite", ["cree_at"])
    op.create_index("ix_activite_contact_cree", "activite", ["contact_id", "cree_at"])
    op.create_index("ix_activite_organisation_cree", "activite", ["organisation_id", "cree_at"])

    op.create_table(
        "texte_pas",
        _id(),
        sa.Column("sequence", _s(40), nullable=False),
        sa.Column("pas", sa.Integer(), nullable=False),
        sa.Column("sujet", _s(200), nullable=True),
        sa.Column("corps", sa.Text(), nullable=False),
        sa.Column("maj_par_id", sa.Integer(), sa.ForeignKey("membre.id"), nullable=True),
        _date("maj_at"),
        sa.UniqueConstraint("sequence", "pas", name="uq_texte_pas_sequence_pas"),
    )

    reglage = op.create_table(
        "reglage",
        _id(),
        sa.Column("relances_en_pause", sa.Boolean(), nullable=False),
        sa.Column("creneau_jours", _s(20), nullable=False),
        sa.Column("creneau_debut", sa.Integer(), nullable=False),
        sa.Column("creneau_fin", sa.Integer(), nullable=False),
        sa.Column("expediteur_nom", _s(80), nullable=False),
        sa.Column("expediteur_email", _s(254), nullable=False),
        sa.Column("reponse_a", _s(254), nullable=True),
        sa.Column("lien_rdv", _s(300), nullable=True),
        sa.Column("lien_creation_compte", _s(300), nullable=True),
        _date("pilote_ouvert_at", nullable=True),
        sa.Column("sequences_coupees", sa.Text(), nullable=False),
        sa.Column("prospection_departements", sa.Text(), nullable=False),
        sa.Column("prospection_effectif_min", sa.Integer(), nullable=False),
        sa.Column("prospection_postes", sa.Text(), nullable=False),
        sa.Column("prospection_plafond_jour", sa.Integer(), nullable=False),
        sa.Column("prospection_seuil", sa.Integer(), nullable=False),
        sa.Column("linkedin_etat", _s(20), nullable=False),
        _date("linkedin_etat_at", nullable=True),
        _date("maj_at"),
        sa.CheckConstraint("id = 1", name="ck_reglage_ligne_unique"),
        _dans("reglage", "linkedin_etat", ("inconnu", "ok", "a_reconnecter", "non_configure")),
    )

    op.create_table(
        "passage_prospection",
        _id(),
        sa.Column("cle", _s(60), nullable=False),
        sa.Column("declencheur", _s(10), nullable=False),
        sa.Column("statut", _s(10), nullable=False),
        _date("debut_at"),
        _date("fin_at", nullable=True),
        sa.Column("entreprises_vues", sa.Integer(), nullable=False),
        sa.Column("nouvelles", sa.Integer(), nullable=False),
        sa.Column("decideurs", sa.Integer(), nullable=False),
        sa.Column("en_sequence", sa.Integer(), nullable=False),
        sa.Column("erreur", _s(500), nullable=True),
        sa.UniqueConstraint("cle", name="uq_passage_prospection_cle"),
        _dans("passage_prospection", "declencheur", ("cron", "manuel")),
        _dans("passage_prospection", "statut", ("en_cours", "fini", "erreur")),
    )

    op.create_table(
        "verrou",
        sa.Column("nom", _s(40), primary_key=True),
        sa.Column("jeton", _s(40), nullable=False),
        _date("expire_at"),
    )

    op.create_table(
        "webhook_recu",
        _id(),
        sa.Column("fournisseur", _s(30), nullable=False),
        sa.Column("cle", _s(120), nullable=False),
        _date("recu_at"),
        sa.UniqueConstraint("fournisseur", "cle", name="uq_webhook_recu_fournisseur_cle"),
    )

    # Seule donnée insérée : la ligne de réglages, avec ses valeurs par défaut.
    op.bulk_insert(reglage, [{
        "id": 1,
        "relances_en_pause": False,
        "creneau_jours": "1,2,3,4,5",
        "creneau_debut": 9,
        "creneau_fin": 18,
        "expediteur_nom": "",
        "expediteur_email": "",
        "sequences_coupees": "[]",
        "prospection_departements": '["67"]',
        "prospection_effectif_min": 50,
        "prospection_postes": '["DRH","RH","RSE","QVT","People"]',
        "prospection_plafond_jour": 20,
        "prospection_seuil": 6,
        "linkedin_etat": "inconnu",
        "maj_at": temps.maintenant(),
    }])


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
