from __future__ import annotations

import datetime as dt

import pytest
import sqlalchemy as sa
from alembic import command
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app import journal, pipelines, verrou
from app.modeles import (
    Activite, Affaire, Contact, Envoi, InscriptionSequence, Membre, Organisation, Reglage,
)
from conftest import alembic_config

T0 = dt.datetime(2026, 10, 12, 8, 0, 0)

TABLES = {
    "membre", "jeton_connexion", "organisation", "contact", "affaire", "activite",
    "inscription_sequence", "envoi", "texte_pas", "reglage", "passage_prospection",
    "verrou", "webhook_recu",
}


def _contact(**kw) -> Contact:
    base = dict(type="donateur", prenom="Prénom", source="landing", cree_at=T0, maj_at=T0)
    return Contact(**{**base, **kw})


def _organisation(**kw) -> Organisation:
    base = dict(type="entreprise", nom="Entreprise Test 1", source="prospection", cree_at=T0, maj_at=T0)
    return Organisation(**{**base, **kw})


def _ajouter_refuse(session: Session, *objets) -> None:
    with pytest.raises(IntegrityError):
        for o in objets:
            session.add(o)
            session.commit()
    session.rollback()


def test_migration_0001_correspond_aux_modeles(engine):
    assert TABLES <= set(sa.inspect(engine).get_table_names())
    command.check(alembic_config())  # lève si les modèles et la base diffèrent


def test_downgrade_supprime_toutes_les_tables(engine):
    command.downgrade(alembic_config(), "base")
    restantes = set(sa.inspect(engine).get_table_names()) - {"alembic_version"}
    assert restantes == set()


def test_email_contact_unique_insensible_a_la_casse(session):
    session.add(_contact(email="  Prenom@Exemple.test "))
    session.commit()
    assert session.exec(select(Contact.email)).one() == "prenom@exemple.test"
    _ajouter_refuse(session, _contact(email="PRENOM@exemple.TEST"))


def test_email_membre_normalise(session):
    session.add(Membre(email=" Prenom@Exemple.TEST", prenom="Prénom Test", role="equipe", cree_at=T0))
    session.commit()
    assert session.exec(select(Membre.email)).one() == "prenom@exemple.test"


def test_contact_sans_aucun_identifiant_refuse(session):
    _ajouter_refuse(session, _contact(prenom=None))


def test_siren_unique(session):
    session.add(_organisation(siren="000000001"))
    session.add(_organisation(nom="Entreprise Test 2"))  # plusieurs NULL permis
    session.add(_organisation(nom="Entreprise Test 3"))
    session.commit()
    _ajouter_refuse(session, _organisation(nom="Entreprise Test 4", siren="000000001"))


def test_note_hors_0_10_refusee(session):
    _ajouter_refuse(session, _organisation(note=11))


def test_linkedin_provider_id_unique(session):
    session.add(_contact(linkedin_provider_id="profil-test-1", type="entreprise", source="prospection"))
    session.add(_contact(prenom="Autre"))
    session.commit()
    _ajouter_refuse(session, _contact(linkedin_provider_id="profil-test-1"))


def _inscription(session: Session) -> InscriptionSequence:
    c = _contact(email="prenom@exemple.test")
    session.add(c)
    session.commit()
    i = InscriptionSequence(contact_id=c.id, sequence="donateur-bienvenue", pas_courant=1,
                            prochain_envoi_at=T0, ancre_at=T0, statut="active", cree_at=T0, maj_at=T0)
    session.add(i)
    session.commit()
    return i


def test_envoi_unique_inscription_pas(session):
    i = _inscription(session)

    def envoi(pas: int) -> Envoi:
        return Envoi(inscription_id=i.id, pas=pas, canal="email", statut="en_cours", cree_at=T0, maj_at=T0)

    session.add(envoi(1))
    session.add(envoi(2))
    session.commit()
    _ajouter_refuse(session, envoi(1))


def test_affaire_unique_contact_pipeline(session):
    c = _contact(email="prenom@exemple.test")
    session.add(c)
    session.commit()

    def affaire(pipeline: str, etape: str) -> Affaire:
        return Affaire(pipeline=pipeline, etape=etape, etape_depuis=T0, contact_id=c.id, cree_at=T0, maj_at=T0)

    session.add(affaire("donateurs", "inscrit"))
    session.add(affaire("entreprises", "prospect"))
    session.commit()
    _ajouter_refuse(session, affaire("donateurs", "fidele"))
    _ajouter_refuse(session, Affaire(pipeline="donateurs", etape="inscrit", etape_depuis=T0, cree_at=T0, maj_at=T0))


def test_inscription_unique_contact_sequence(session):
    i = _inscription(session)
    _ajouter_refuse(session, InscriptionSequence(
        contact_id=i.contact_id, sequence="donateur-bienvenue", pas_courant=1, ancre_at=T0,
        statut="active", cree_at=T0, maj_at=T0))


def test_valeur_hors_liste_refusee(session):
    _ajouter_refuse(session, _contact(type="inconnu"))


def test_reglage_ligne_unique_creee_par_migration(session):
    r = session.exec(select(Reglage)).one()
    assert r.id == 1
    assert (r.relances_en_pause, r.creneau_jours, r.creneau_debut, r.creneau_fin) == (False, "1,2,3,4,5", 9, 18)
    assert r.prospection_departements == '["67"]'
    assert r.prospection_postes == '["DRH","RH","RSE","QVT","People"]'
    assert (r.prospection_effectif_min, r.prospection_plafond_jour, r.prospection_seuil) == (50, 20, 6)
    assert (r.sequences_coupees, r.linkedin_etat) == ("[]", "inconnu")
    assert r.pilote_ouvert_at is None
    autre = Reglage(**{**r.model_dump(), "id": 2})
    session.expunge(r)
    _ajouter_refuse(session, autre)


def test_base_vide_aucune_donnee_hors_reglage(engine):
    with engine.connect() as conn:
        for table in TABLES - {"reglage"}:
            assert conn.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar() == 0, table
        assert conn.execute(sa.text("SELECT COUNT(*) FROM reglage")).scalar() == 1


def test_expediteur_copie_depuis_l_environnement_au_demarrage(client, session):
    r = session.exec(select(Reglage)).one()
    assert (r.expediteur_nom, r.expediteur_email) == ("MERCI", "bonjour@exemple.test")


# Pipelines

def test_pipelines_etapes_et_libelles():
    assert pipelines.cles_etapes("donateurs") == [
        "inscrit", "bienvenue_envoyee", "pilote_ouvert", "compte_cree", "premier_don", "fidele", "perdu"]
    assert pipelines.cles_etapes("associations")[-1] == "perdue"
    assert pipelines.etape("entreprises", "a_repondu") == {"cle": "a_repondu", "nom": "A répondu"}
    assert pipelines.RATTACHE["entreprises"]["contacte"] == "relancer"
    assert "perdu" not in pipelines.RATTACHE["donateurs"]


def test_pipelines_jamais_de_recul_automatique():
    assert pipelines.avance("donateurs", "inscrit", "bienvenue_envoyee")
    assert not pipelines.avance("donateurs", "premier_don", "compte_cree")
    assert not pipelines.avance("donateurs", "perdu", "fidele")
    assert not pipelines.avance("donateurs", "inscrit", "perdu")


# Verrou

def test_verrou_prise_conflit_expiration_relache(session, horloge):
    j1 = verrou.prendre(session, "tick", dt.timedelta(minutes=5))
    assert j1
    assert verrou.prendre(session, "tick", dt.timedelta(minutes=5)) is None
    horloge.avancer(minutes=6)
    j2 = verrou.prendre(session, "tick", dt.timedelta(minutes=5))
    assert j2 and j2 != j1
    verrou.relacher(session, "tick", j1)  # ancien détenteur : sans effet
    assert verrou.prendre(session, "tick", dt.timedelta(minutes=5)) is None
    verrou.relacher(session, "tick", j2)
    assert verrou.prendre(session, "tick", dt.timedelta(minutes=5))


# Journal

def test_journal_ajoute_une_activite_horodatee(session, horloge):
    c = _contact(email="prenom@exemple.test")
    session.add(c)
    session.commit()
    a = journal.ajouter_activite(session, "note", "Note ajoutée", texte="Appel prévu",
                                 contact_id=c.id, donnees={"a": 1})
    session.commit()
    lu = session.get(Activite, a.id)
    assert (lu.type, lu.cree_at, lu.donnees) == ("note", horloge.t, '{"a": 1}')


def test_journal_refuse_un_type_inconnu(session):
    with pytest.raises(ValueError):
        journal.ajouter_activite(session, "inconnu", "Titre")
