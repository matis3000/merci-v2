"""Capture publique : POST /public/inscription (section 4.10)."""
from __future__ import annotations

import json
import time

from sqlmodel import select

from app import securite
from app.modeles import Activite, Affaire, Contact, InscriptionSequence, Organisation, Reglage
from conftest import TEXTE_CONSENTEMENT, corps_inscription, creer_membre, inscrire_landing

ORIGINE_LANDING = "http://127.0.0.1:5500"


def _contact(session, email="prenom@exemple.test") -> Contact:
    return session.exec(select(Contact).where(Contact.email == email)).one()


def _types_activite(session, contact_id) -> list[str]:
    return [a.type for a in session.exec(
        select(Activite).where(Activite.contact_id == contact_id).order_by(Activite.id))]


def test_profil_donateur_affaire_inscrit_et_sequence_bienvenue(client, session, horloge, sans_envoi_immediat):
    r = inscrire_landing(client, "donateur", source_detail="instagram")
    assert r.status_code == 201 and r.json() == {"ok": True}

    c = _contact(session)
    assert (c.type, c.prenom, c.source, c.source_detail) == ("donateur", "Prénom Test", "landing", "instagram")
    assert c.consentement_at == horloge.t and c.consentement_texte == TEXTE_CONSENTEMENT
    assert c.organisation_id is None

    affaire = session.exec(select(Affaire).where(Affaire.contact_id == c.id)).one()
    assert (affaire.pipeline, affaire.etape, affaire.etape_depuis) == ("donateurs", "inscrit", horloge.t)

    insc = session.exec(select(InscriptionSequence).where(InscriptionSequence.contact_id == c.id)).one()
    assert (insc.sequence, insc.statut, insc.pas_courant) == ("donateur-bienvenue", "active", 1)
    assert insc.prochain_envoi_at == horloge.t and insc.ancre_at == horloge.t

    assert _types_activite(session, c.id) == ["inscription", "sequence_inscrite"]
    act = session.exec(select(Activite).where(Activite.type == "inscription")).one()
    assert act.titre == "Inscription via la landing"
    donnees = json.loads(act.donnees)
    assert donnees["date"] == "2026-10-12T07:59:00.000Z" and donnees["source"] == "landing-v1-galet"
    assert act.cree_at == horloge.t  # la date fournie n'est jamais l'horodatage de référence


def test_profil_entreprise_organisation_affaire_prospect_et_sequence_entrante(client, session, sans_envoi_immediat):
    assert inscrire_landing(client, "entreprise", structure="Entreprise Test 1").status_code == 201
    c = _contact(session)
    assert c.type == "entreprise" and c.source_detail == "landing-v1-galet"  # source à défaut de détail
    org = session.get(Organisation, c.organisation_id)
    assert (org.type, org.nom, org.source) == ("entreprise", "Entreprise Test 1", "landing")

    affaire = session.exec(select(Affaire).where(Affaire.contact_id == c.id)).one()
    assert (affaire.pipeline, affaire.etape, affaire.organisation_id) == ("entreprises", "prospect", org.id)
    insc = session.exec(select(InscriptionSequence)).one()
    assert (insc.contact_id, insc.sequence) == (c.id, "entreprise-entrante")

    # Même structure écrite autrement : même organisation.
    inscrire_landing(client, "entreprise", email="autre@exemple.test", structure="  entreprise TEST 1 ")
    assert len(session.exec(select(Organisation)).all()) == 1
    assert _contact(session, "autre@exemple.test").organisation_id == org.id


def test_profil_association_bienvenue_et_equipe_notifiee(
        client, session, admin, fournisseurs_factices, sans_envoi_immediat):
    creer_membre(session, "equipe@exemple.test")
    creer_membre(session, "parti@exemple.test", actif=False)
    r = inscrire_landing(client, "association", email="asso@exemple.test", structure="Association Test 1")
    assert r.status_code == 201

    c = _contact(session, "asso@exemple.test")
    org = session.get(Organisation, c.organisation_id)
    assert (c.type, org.type, org.nom) == ("association", "association", "Association Test 1")
    affaire = session.exec(select(Affaire).where(Affaire.contact_id == c.id)).one()
    assert (affaire.pipeline, affaire.etape) == ("associations", "inscrite")
    [insc] = session.exec(select(InscriptionSequence)).all()
    assert (insc.sequence, insc.contact_id) == ("association-bienvenue", c.id)

    envois = [json.loads(p.read_text()) for p in fournisseurs_factices.emails()]
    assert sorted(e["a"] for e in envois) == ["admin@exemple.test", "equipe@exemple.test"]
    assert all("Association Test 1" in e["sujet"] + e["texte"] for e in envois)


def test_doublon_email_casse_differente_pas_de_second_contact(client, session):
    assert inscrire_landing(client, email="Prenom@Exemple.TEST").status_code == 201
    assert inscrire_landing(client, email="  prenom@exemple.test ").status_code == 201
    assert len(session.exec(select(Contact)).all()) == 1
    assert len(session.exec(select(Affaire)).all()) == 1
    assert len(session.exec(select(InscriptionSequence)).all()) == 1


def test_doublon_ajoute_activite_reinscription(client, session, sans_envoi_immediat):
    inscrire_landing(client)
    r = inscrire_landing(client, prenom="Autre Prénom")
    assert r.status_code == 201 and r.json() == {"ok": True}  # pas d'énumération
    c = _contact(session)
    assert c.prenom == "Prénom Test"  # seuls les champs vides sont complétés
    assert _types_activite(session, c.id) == ["inscription", "sequence_inscrite", "reinscription"]


def test_consentement_absent_refuse_422(client, session):
    for valeur in (None, False, "oui"):
        corps = corps_inscription()
        if valeur is None:
            corps.pop("consentement")
        else:
            corps["consentement"] = valeur
        r = client.post("/public/inscription", json=corps)
        assert r.status_code == 422 and r.json() == {"detail": "Consentement obligatoire"}
    assert session.exec(select(Contact)).all() == []


def test_consentement_texte_absent_refuse_422(client, session):
    for corps in (corps_inscription(consentement_texte=""), {k: v for k, v in corps_inscription().items()
                                                             if k != "consentement_texte"}):
        r = client.post("/public/inscription", json=corps)
        assert r.status_code == 422 and r.json() == {"detail": "Consentement obligatoire"}
    assert session.exec(select(Contact)).all() == []


def test_email_invalide_422(client, session):
    for email in ("pas-une-adresse", "a@b", "", "prenom @exemple.test"):
        r = inscrire_landing(client, email=email)
        assert r.status_code == 422 and r.json() == {"detail": "Adresse e-mail invalide"}
    assert session.exec(select(Contact)).all() == []


def test_structure_obligatoire_hors_donateur(client, session):
    for profil in ("entreprise", "association"):
        securite.reinitialiser_limites()  # 7 requêtes : au-delà de la limite de 5 par minute
        for structure in ("", "   ", None):
            corps = corps_inscription(profil, structure=structure)
            if structure is None:
                corps.pop("structure")
            r = client.post("/public/inscription", json=corps)
            assert r.status_code == 422 and r.json() == {"detail": "Nom de la structure obligatoire"}
    assert session.exec(select(Contact)).all() == []
    assert inscrire_landing(client, "donateur", structure="").status_code == 201


def test_profil_inconnu_422_forme_native(client):
    r = inscrire_landing(client, "robot")
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)


def test_champ_piege_rempli_201_sans_ecriture(client, session, fournisseurs_factices):
    r = inscrire_landing(client, "association", site_web="http://exemple.test")
    assert r.status_code == 201 and r.json() == {"ok": True}
    assert session.exec(select(Contact)).all() == []
    assert session.exec(select(Activite)).all() == []
    assert fournisseurs_factices.emails() == []
    assert inscrire_landing(client, site_web="").status_code == 201
    assert len(session.exec(select(Contact)).all()) == 1


def test_limite_5_par_ip_et_par_minute_429(client, session, horloge):
    for i in range(5):
        assert inscrire_landing(client, email=f"prenom{i}@exemple.test").status_code == 201
    r = inscrire_landing(client, email="prenom9@exemple.test")
    assert r.status_code == 429 and r.json() == {"detail": "Trop d'envois, réessayez dans une minute"}
    # Les requêtes invalides comptent aussi.
    assert inscrire_landing(client, email="invalide").status_code == 429
    horloge.avancer(seconds=61)
    assert inscrire_landing(client, email="prenom9@exemple.test").status_code == 201
    assert len(session.exec(select(Contact)).all()) == 6


def test_cors_origine_landing_autorisee_autre_refusee(client):
    pre = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    ok = client.options("/public/inscription", headers={"Origin": ORIGINE_LANDING, **pre})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == ORIGINE_LANDING
    assert "POST" in ok.headers["access-control-allow-methods"]
    assert "access-control-allow-credentials" not in ok.headers

    refuse = client.options("/public/inscription", headers={"Origin": "https://autre.exemple.test", **pre})
    assert refuse.status_code == 400
    assert "access-control-allow-origin" not in refuse.headers

    r = client.post("/public/inscription", json=corps_inscription(), headers={"Origin": ORIGINE_LANDING})
    assert r.status_code == 201 and r.headers["access-control-allow-origin"] == ORIGINE_LANDING
    r = client.post("/public/inscription", json=corps_inscription(email="autre@exemple.test"),
                    headers={"Origin": "https://autre.exemple.test"})
    assert "access-control-allow-origin" not in r.headers


def test_reponse_en_moins_de_5_secondes(client):
    debut = time.perf_counter()
    assert inscrire_landing(client, "entreprise").status_code == 201
    assert time.perf_counter() - debut < 5


def test_envoi_immediat_dans_le_creneau(client, session, horloge, fournisseurs_factices):
    """Lundi 10 h à Paris : l'e-mail de bienvenue part juste après la réponse, sans attendre le tick."""
    assert inscrire_landing(client).status_code == 201
    [fichier] = fournisseurs_factices.emails()
    mail = json.loads(fichier.read_text())
    assert (mail["a"], mail["sujet"]) == ("prenom@exemple.test", "Bienvenue chez MERCI")
    assert mail["entetes"]["List-Unsubscribe"].startswith("<http://127.0.0.1:8010/public/desinscription/")
    session.expire_all()
    insc = session.exec(select(InscriptionSequence)).one()
    assert (insc.statut, insc.pas_courant) == ("terminee", 2)
    assert session.exec(select(Affaire)).one().etape == "bienvenue_envoyee"
    inscrire_landing(client)  # contact déjà inscrit : aucune nouvelle inscription, aucun second e-mail
    assert len(fournisseurs_factices.emails()) == 1


def test_envoi_differe_hors_creneau(client, session, horloge, fournisseurs_factices):
    horloge.avancer(days=5)  # samedi 17/10/2026, 10 h à Paris
    assert inscrire_landing(client).status_code == 201
    insc = session.exec(select(InscriptionSequence)).one()
    assert fournisseurs_factices.emails() == []
    # Le pas reste dû : il partira au premier tick dans le créneau.
    assert insc.statut == "active" and insc.pas_courant == 1 and insc.prochain_envoi_at <= horloge.t


def test_reinscription_apres_desinscription_retablit_le_consentement(client, session, horloge):
    inscrire_landing(client)
    c = _contact(session)
    c.desinscrit_at = horloge.t
    session.add(c)
    session.commit()
    horloge.avancer(days=2)
    inscrire_landing(client, consentement_texte="Nouveau texte de la case.")
    session.refresh(c)
    assert c.desinscrit_at is None
    assert c.consentement_at == horloge.t and c.consentement_texte == "Nouveau texte de la case."


def test_inscription_donateur_apres_ouverture_du_pilote(client, session, horloge):
    r = session.get(Reglage, 1)
    r.pilote_ouvert_at = horloge.t
    session.add(r)
    session.commit()
    inscrire_landing(client)
    c = _contact(session)
    affaire = session.exec(select(Affaire).where(Affaire.contact_id == c.id)).one()
    assert (affaire.pipeline, affaire.etape) == ("donateurs", "pilote_ouvert")
    sequences = [i.sequence for i in session.exec(select(InscriptionSequence))]
    assert sequences == ["donateur-pilote"]


def test_libelle_de_source_affiche_avec_majuscule(client, session, sans_envoi_immediat):
    """Le détail de source est conservé tel quel, mais affiché avec une majuscule (« Instagram »)."""
    inscrire_landing(client, "donateur", source_detail="instagram")
    c = _contact(session)
    assert c.source_detail == "instagram"
    act = session.exec(select(Activite).where(Activite.contact_id == c.id, Activite.type == "inscription")).one()
    assert act.texte == "Source : Instagram."
