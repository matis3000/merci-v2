"""Événements de l'App MERCI : POST /public/evenement (section 4.10, décision D11)."""
from __future__ import annotations

from sqlmodel import select

from app.modeles import Activite, Affaire, Contact, InscriptionSequence
from conftest import creer_affaire, creer_contact, creer_inscription

CLE = {"X-Cle-App": "dev-cle-app"}


def _evenement(client, type, email="prenom@exemple.test", **kw):
    return client.post("/public/evenement", json={"email": email, "type": type, **kw}, headers=CLE)


def _donateur(session, etape="inscrit") -> tuple[Contact, Affaire]:
    c = creer_contact(session, email="prenom@exemple.test")
    return c, creer_affaire(session, "donateurs", etape, contact_id=c.id)


def test_cle_invalide_401(client, session):
    _donateur(session)
    corps = {"email": "prenom@exemple.test", "type": "don"}
    assert client.post("/public/evenement", json=corps).status_code == 401
    assert client.post("/public/evenement", json=corps, headers={"X-Cle-App": "mauvaise"}).status_code == 401
    assert session.exec(select(Activite)).all() == []


def test_corps_invalide_422(client):
    assert _evenement(client, "inconnu").status_code == 422


def test_compte_cree_avance_et_arrete_sequence_pilote(client, session, horloge):
    c, affaire = _donateur(session, "pilote_ouvert")
    pilote = creer_inscription(session, c.id, "donateur-pilote", pas_courant=2,
                               prochain_envoi_at=horloge.t)
    horloge.avancer(hours=1)
    r = _evenement(client, "compte_cree", email="Prenom@Exemple.test")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "connu": True, "etape": "compte_cree"}

    session.refresh(affaire)
    session.refresh(pilote)
    assert affaire.etape == "compte_cree" and affaire.etape_depuis == horloge.t
    assert (pilote.statut, pilote.raison_arret, pilote.prochain_envoi_at) == ("arretee", "objectif_atteint", None)
    types = [a.type for a in session.exec(select(Activite).where(Activite.contact_id == c.id))]
    assert "evenement_app" in types and "sequence_arretee" in types and "etape_changee" in types


def test_don_premier_don_puis_fidele(client, session):
    _, affaire = _donateur(session, "compte_cree")
    assert _evenement(client, "don").json()["etape"] == "premier_don"
    assert _evenement(client, "don").json()["etape"] == "fidele"
    session.refresh(affaire)
    assert affaire.etape == "fidele"
    assert len(session.exec(select(Activite).where(Activite.type == "evenement_app")).all()) == 2


def test_don_suivi_fidele(client, session):
    _, affaire = _donateur(session, "inscrit")
    assert _evenement(client, "don_suivi", at="2026-10-12T07:00:00Z").json() == {
        "ok": True, "connu": True, "etape": "fidele"}
    session.refresh(affaire)
    assert affaire.etape == "fidele"


def test_email_inconnu_connu_false_rien_cree(client, session):
    r = _evenement(client, "compte_cree", email="inconnu@exemple.test")
    assert r.json() == {"ok": True, "connu": False, "etape": None}
    assert session.exec(select(Contact)).all() == []
    assert session.exec(select(Affaire)).all() == []
    assert session.exec(select(Activite)).all() == []


def test_jamais_de_recul_d_etape(client, session):
    c, affaire = _donateur(session, "fidele")
    for type in ("compte_cree", "don", "don_suivi"):
        assert _evenement(client, type).json()["etape"] == "fidele"
    session.refresh(affaire)
    assert affaire.etape == "fidele"
    # Une affaire perdue n'est pas déplacée automatiquement.
    affaire.etape = "perdu"
    session.add(affaire)
    session.commit()
    assert _evenement(client, "don").json()["etape"] == "perdu"
    assert [a.type for a in session.exec(select(Activite).where(Activite.type == "etape_changee"))] == []
    assert session.exec(select(InscriptionSequence)).all() == []
