"""Synchro HubSpot (lot L8) : table de correspondance et réglages de la synchro.

Crée `synchro_hubspot` (identifiant HubSpot, état, essais, dernière erreur, dernière synchro de
chaque contact, organisation et affaire) et ajoute à `reglage` la correspondance des étapes et la
date de création des propriétés MERCI dans HubSpot. Aucune donnée insérée.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "synchro_hubspot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("objet_type", sa.String(length=20), nullable=False),
        sa.Column("objet_id", sa.Integer(), nullable=False),
        sa.Column("hubspot_id", sa.String(length=40), nullable=True),
        sa.Column("etat", sa.String(length=20), nullable=False),
        sa.Column("essais", sa.Integer(), nullable=False),
        sa.Column("derniere_erreur", sa.String(length=500), nullable=True),
        sa.Column("prochain_essai_at", sa.DateTime(), nullable=True),
        sa.Column("synchro_at", sa.DateTime(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("cree_at", sa.DateTime(), nullable=False),
        sa.Column("maj_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("objet_type", "objet_id", name="uq_synchro_hubspot_objet"),
        sa.CheckConstraint("objet_type IN ('contact', 'organisation', 'affaire')", name="ck_synchro_hubspot_objet_type"),
        sa.CheckConstraint("etat IN ('a_synchroniser', 'ok', 'erreur')", name="ck_synchro_hubspot_etat"),
    )
    op.create_index("ix_synchro_hubspot_etat_prochain", "synchro_hubspot", ["etat", "prochain_essai_at"])
    # ADD COLUMN simple (SQLite et Postgres) : pas de recréation de `reglage`, ses CHECK restent en place.
    op.add_column("reglage", sa.Column("hubspot_etapes", sa.Text(), nullable=False, server_default="{}"))
    op.add_column("reglage", sa.Column("hubspot_proprietes_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("reglage", "hubspot_proprietes_at")
    op.drop_column("reglage", "hubspot_etapes")
    op.drop_index("ix_synchro_hubspot_etat_prochain", table_name="synchro_hubspot")
    op.drop_table("synchro_hubspot")
