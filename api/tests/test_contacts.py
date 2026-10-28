"""Contacts, organisations, fiche, fil, import et export CSV (section 4.6), pause et inscription
manuelle (section 4.7)."""
from __future__ import annotations

import pytest
from sqlmodel import select

from app.modeles import Activite, Affaire, Contact, InscriptionSequence, Organisation
from conftest import (
    CLES_ACTIVITE, CLES_AFFAIRE, CLES_CONTACT, CLES_ETAT_SEQUENCE, CLES_FICHE, CLES_LIGNE, CLES_ORGANISATION,
    CLES_PASDEF, CLES_SEQUENCEDEF, creer_affaire, creer_contact, creer_inscription, creer_organisation,
    inscrire_landing,
)

# L'état juste après la capture : l'envoi immédiat est testé dans test_inscription.py.
pytestmark = pytest.mark.usefixtures("sans_envoi_immediat")

ENTETE_CSV = ("type;prenom;nom;email;telephone;poste;organisation;ville;linkedin_url;source;source_detail;"
              "pipeline;etape;note;sequence;etat_sequence;cree_at")


def _jeu(client, session, horloge):
    """Un donateur de la landing, un donateur saisi à la main, un décideur trouvé par la
    prospection, une entreprise sans décideur."""
    inscrire_landing(client, email="landing@exemple.test", prenom="Prénom Landing", source_detail="instagram")
    horloge.avancer(minutes=1)
    client.post("/contacts", json={"type": "donateur", "prenom": "Prénom Manuel", "email": "manuel@exemple.test",
                                   "ville": "Ville Test"})
    horloge.avancer(minutes=1)
    org = creer_organisation(session, "Entreprise Test 1", siren="000000001", note=7, tranche_effectif="32",
                             raisons_note='["Décideur RH trouvé +4", "250 salariés et plus +3"]')
    decideur = creer_contact(session, type="entreprise", prenom="Prénom", nom="Décideur", poste="DRH",
                             organisation_id=org.id, source="prospection", source_detail="Registre + LinkedIn",
                             linkedin_provider_id="factice-1")
    creer_affaire(session, "entreprises", "contacte", contact_id=decideur.id, organisation_id=org.id)
    creer_inscription(session, decideur.id, "entreprise-prospection", pas_courant=2, prochain_envoi_at=None)
    horloge.avancer(minutes=1)
    seule = creer_organisation(session, "Entreprise Test 2", siren="000000002", note=3)
    creer_affaire(session, "entreprises", "prospect", organisation_id=seule.id)
    return decideur, org, seule


def _noms(client, **params):
    r = client.get("/contacts", params=params)
    assert r.status_code == 200, r.text
    return [ligne["nom_affiche"] for ligne in r.json()["lignes"]]


# --------------------------------------------------------------------------- liste

def test_liste_base_vide(client_connecte):
    assert client_connecte.get("/contacts").json() == {
        "total": 0, "page": 1, "par_page": 50, "resume": {"landing": 0, "prospection": 0}, "lignes": []}


def test_liste_filtres_type_source_etape_note_sequence(client_connecte, session, horloge):
    _jeu(client_connecte, session, horloge)
    rep = client_connecte.get("/contacts").json()
    assert rep["total"] == 4 and rep["resume"] == {"landing": 1, "prospection": 2}
    assert [ligne["nom_affiche"] for ligne in rep["lignes"]] == [
        "Entreprise Test 2", "Prénom Décideur", "Prénom Manuel", "Prénom Landing"]  # cree_at décroissant
    assert all(set(ligne) == CLES_LIGNE for ligne in rep["lignes"])

    assert _noms(client_connecte, type="donateur") == ["Prénom Manuel", "Prénom Landing"]
    assert _noms(client_connecte, type="entreprise") == ["Entreprise Test 2", "Prénom Décideur"]
    assert _noms(client_connecte, source="prospection") == ["Entreprise Test 2", "Prénom Décideur"]
    assert _noms(client_connecte, source="manuel") == ["Prénom Manuel"]
    assert _noms(client_connecte, pipeline="entreprises", etape="contacte") == ["Prénom Décideur"]
    assert _noms(client_connecte, pipeline="donateurs") == ["Prénom Manuel", "Prénom Landing"]
    assert _noms(client_connecte, note_min=5) == ["Prénom Décideur"]
    assert _noms(client_connecte, note_min=0) == ["Entreprise Test 2", "Prénom Décideur"]
    assert _noms(client_connecte, sequence="donateur-bienvenue") == ["Prénom Landing"]
    assert _noms(client_connecte, etat_sequence="due") == ["Prénom Landing"]
    assert _noms(client_connecte, etat_sequence="active") == ["Prénom Décideur"]

    page = client_connecte.get("/contacts", params={"par_page": 1, "page": 2}).json()
    assert (page["total"], page["page"], page["par_page"]) == (4, 2, 1)
    assert [ligne["nom_affiche"] for ligne in page["lignes"]] == ["Prénom Décideur"]

    for params in ({"type": "robot"}, {"note_min": 11}, {"etat_sequence": "autre"}, {"par_page": 201},
                   {"source": "ailleurs"}, {"pipeline": "autre"}, {"sequence": "autre"}, {"page": 0}):
        assert client_connecte.get("/contacts", params=params).status_code == 422, params


def test_ligne_decideur_forme(client_connecte, session, horloge):
    decideur, org, _ = _jeu(client_connecte, session, horloge)
    lignes = client_connecte.get("/contacts").json()["lignes"]
    ligne = next(x for x in lignes if x["id"] == decideur.id and x["genre"] == "contact")
    assert ligne["sous_titre"] == "DRH, Entreprise Test 1"
    assert ligne["organisation"] == {"id": org.id, "nom": "Entreprise Test 1"} and ligne["note"] == 7
    assert ligne["affaire"] == {"id": ligne["affaire"]["id"], "pipeline": "entreprises",
                                "etape": {"cle": "contacte", "nom": "Contacté"}}
    seq = ligne["sequence"]
    assert set(seq) == CLES_ETAT_SEQUENCE
    assert (seq["nom"], seq["pas"], seq["total"], seq["etat"], seq["attente"]) == (
        "Prospection LinkedIn", 2, 4, "active", "acceptation")
    landing = next(x for x in lignes if x["nom_affiche"] == "Prénom Landing")
    assert landing["sous_titre"] == "Donateur" and landing["derniere_activite"]["titre"]
    manuel = next(x for x in lignes if x["nom_affiche"] == "Prénom Manuel")
    assert manuel["sous_titre"] == "Donateur, Ville Test" and manuel["sequence"] is None


def test_recherche_nom_email_entreprise(client_connecte, session, horloge):
    _jeu(client_connecte, session, horloge)
    assert _noms(client_connecte, q="decideur") == ["Prénom Décideur"]  # sans accent ni casse
    assert _noms(client_connecte, q="MANUEL@exemple") == ["Prénom Manuel"]
    assert _noms(client_connecte, q="entreprise test 1") == ["Prénom Décideur"]
    assert _noms(client_connecte, q="Entreprise Test") == ["Entreprise Test 2", "Prénom Décideur"]
    assert _noms(client_connecte, q="introuvable") == []


def test_liste_inclut_organisations_sans_decideur(client_connecte, session, horloge):
    _, _, seule = _jeu(client_connecte, session, horloge)
    ligne = client_connecte.get("/contacts").json()["lignes"][0]
    assert (ligne["genre"], ligne["id"], ligne["nom_affiche"], ligne["sous_titre"]) == (
        "organisation", seule.id, "Entreprise Test 2", "Aucun décideur trouvé")
    assert (ligne["type"], ligne["source"], ligne["note"], ligne["sequence"]) == ("entreprise", "prospection", 3, None)
    assert ligne["organisation"] == {"id": seule.id, "nom": "Entreprise Test 2"}
    assert ligne["affaire"]["etape"]["cle"] == "prospect"
    # Une organisation qui a un contact n'apparaît pas en double.
    assert len(client_connecte.get("/contacts").json()["lignes"]) == 4


# --------------------------------------------------------------------------- fiche

def test_fiche_contact_forme_du_contrat(client_connecte, session, horloge):
    inscrire_landing(client_connecte, "entreprise", structure="Entreprise Test 1")
    c = session.exec(select(Contact)).one()
    collegue = creer_contact(session, type="entreprise", prenom="Collègue", nom="Test", poste="RSE",
                             organisation_id=c.organisation_id, source="manuel")
    r = client_connecte.get(f"/contacts/{c.id}")
    assert r.status_code == 200
    f = r.json()
    assert set(f) == CLES_FICHE and (f["genre"], f["id"]) == ("contact", c.id)
    assert set(f["contact"]) == CLES_CONTACT and set(f["organisation"]) == CLES_ORGANISATION
    assert set(f["affaire"]) == CLES_AFFAIRE and f["affaire"]["etape"]["cle"] == "prospect"
    assert f["contact"]["consentement_at"] == "2026-10-12T08:00:00Z"
    assert f["autres_contacts"] == [{"id": collegue.id, "nom_affiche": "Collègue Test", "poste": "RSE"}]

    seq = f["sequence"]
    assert set(seq) == {"etat", "definition", "envois"}
    assert set(seq["etat"]) == CLES_ETAT_SEQUENCE and seq["envois"] == []
    assert set(seq["definition"]) == CLES_SEQUENCEDEF and seq["definition"]["cle"] == "entreprise-entrante"
    assert all(set(p) == CLES_PASDEF for p in seq["definition"]["pas"])
    assert [p["delai_libelle"] for p in seq["definition"]["pas"]] == ["J0", "J+3", "J+7"]
    # entreprise-entrante déjà parcourue ; prospection impossible sans profil LinkedIn.
    assert f["sequences_possibles"] == []

    assert [a["type"] for a in f["activites"]] == ["sequence_inscrite", "inscription"]
    assert all(set(a) == CLES_ACTIVITE for a in f["activites"])
    assert f["activites"][1]["canal"] == "systeme" and f["activites"][1]["fort"] is False
    assert f["activites_suivant"] is None


def test_fiche_organisation_et_404(client_connecte, session):
    org = creer_organisation(session, "Entreprise Test 1", tranche_effectif="32", note=3,
                             raisons_note='["Aucun décideur RH ou RSE trouvé", "250 salariés et plus +3"]')
    creer_affaire(session, "entreprises", "prospect", organisation_id=org.id)
    f = client_connecte.get(f"/organisations/{org.id}").json()
    assert set(f) == CLES_FICHE and (f["genre"], f["contact"], f["sequence"]) == ("organisation", None, None)
    assert f["organisation"]["effectif_libelle"] == "250 à 499 salariés"
    assert f["organisation"]["raisons"] == ["Aucun décideur RH ou RSE trouvé", "250 salariés et plus +3"]
    assert f["affaire"]["etape"]["cle"] == "prospect" and f["sequences_possibles"] == []
    assert client_connecte.get("/organisations/999").status_code == 404
    assert client_connecte.get("/contacts/999").status_code == 404

    r = client_connecte.patch(f"/organisations/{org.id}", json={"ville": "Ville Test", "site_web": "https://exemple.test"})
    assert r.status_code == 200 and r.json()["organisation"]["ville"] == "Ville Test"
    assert client_connecte.patch(f"/organisations/{org.id}", json={"nom": ""}).status_code == 422
    assert client_connecte.patch("/organisations/999", json={"ville": "X"}).status_code == 404


# --------------------------------------------------------------------------- création, modification

def test_creation_manuelle_sans_sequence(client_connecte, session, admin):
    r = client_connecte.post("/contacts", json={
        "type": "entreprise", "prenom": "Prénom", "nom": "Test", "email": "Prenom.Test@Exemple.test",
        "poste": "DRH", "organisation_nom": "Entreprise Test 1"})
    assert r.status_code == 201
    f = r.json()
    assert set(f) == CLES_FICHE
    assert (f["contact"]["source"], f["contact"]["email"]) == ("manuel", "prenom.test@exemple.test")
    assert f["contact"]["consentement_at"] is None
    assert f["organisation"]["nom"] == "Entreprise Test 1"
    assert (f["affaire"]["pipeline"], f["affaire"]["etape"]["cle"]) == ("entreprises", "prospect")
    assert f["sequence"] is None
    assert session.exec(select(InscriptionSequence)).all() == []
    act = session.exec(select(Activite).where(Activite.type == "creation_manuelle")).one()
    assert act.membre_id == admin.id

    doublon = client_connecte.post("/contacts", json={"type": "donateur", "email": "prenom.test@exemple.test"})
    assert doublon.status_code == 409
    assert doublon.json()["contact_id"] == f["id"] and doublon.json()["detail"]
    assert client_connecte.post("/contacts", json={"type": "donateur", "nom": "Seul"}).status_code == 422
    assert client_connecte.post("/contacts", json={"type": "donateur", "email": "invalide"}).status_code == 422
    assert client_connecte.post("/contacts", json={"type": "robot", "prenom": "X"}).status_code == 422


def test_modification_email_deja_pris_409(client_connecte, session):
    a = client_connecte.post("/contacts", json={"type": "donateur", "prenom": "Un", "email": "un@exemple.test"}).json()
    b = client_connecte.post("/contacts", json={"type": "donateur", "prenom": "Deux", "email": "deux@exemple.test"}).json()
    assert client_connecte.patch(f"/contacts/{b['id']}", json={"email": "UN@exemple.test"}).status_code == 409
    r = client_connecte.patch(f"/contacts/{b['id']}", json={"email": "deux@exemple.test", "telephone": "0000000000",
                                                            "linkedin_provider_id": "factice-2"})
    assert r.status_code == 200 and r.json()["contact"]["telephone"] == "0000000000"
    assert client_connecte.patch(f"/contacts/{a['id']}", json={"linkedin_provider_id": "factice-2"}).status_code == 409
    assert client_connecte.patch(f"/contacts/{a['id']}", json={"prenom": None, "email": None}).status_code == 422
    assert client_connecte.patch("/contacts/999", json={"prenom": "X"}).status_code == 404
    r = client_connecte.patch(f"/contacts/{a['id']}", json={"organisation_nom": "Entreprise Test 1"})
    assert r.json()["organisation"]["nom"] == "Entreprise Test 1"


# --------------------------------------------------------------------------- fil d'activité

def test_ajout_note_au_fil(client_connecte, session, admin, horloge):
    c = client_connecte.post("/contacts", json={"type": "donateur", "prenom": "Prénom"}).json()
    horloge.avancer(minutes=1)
    r = client_connecte.post(f"/contacts/{c['id']}/activites", json={"type": "note", "texte": "Rappeler jeudi."})
    assert r.status_code == 201
    act = r.json()
    assert set(act) == CLES_ACTIVITE
    assert (act["type"], act["canal"], act["texte"], act["fort"]) == ("note", "equipe", "Rappeler jeudi.", False)
    assert act["auteur"] == {"id": admin.id, "prenom": "Admin Test"}
    fil = client_connecte.get(f"/contacts/{c['id']}").json()["activites"]
    assert [a["type"] for a in fil] == ["note", "creation_manuelle"]

    assert client_connecte.post(f"/contacts/{c['id']}/activites", json={"type": "note", "texte": ""}).status_code == 422
    assert client_connecte.post(f"/contacts/{c['id']}/activites",
                                json={"type": "email_envoye", "texte": "x"}).status_code == 422
    assert client_connecte.post("/contacts/999/activites", json={"type": "note", "texte": "x"}).status_code == 404

    org = creer_organisation(session)
    r = client_connecte.post(f"/organisations/{org.id}/activites", json={"type": "appel", "texte": "Standard."})
    assert r.status_code == 201
    assert [a["type"] for a in client_connecte.get(f"/organisations/{org.id}/activites").json()["activites"]] == ["appel"]


def test_fil_pagination(client_connecte, session):
    c = client_connecte.post("/contacts", json={"type": "donateur", "prenom": "Prénom"}).json()
    for i in range(54):
        client_connecte.post(f"/contacts/{c['id']}/activites", json={"type": "note", "texte": f"Note {i}"})
    fiche = client_connecte.get(f"/contacts/{c['id']}").json()
    assert len(fiche["activites"]) == 50 and fiche["activites"][0]["texte"] == "Note 53"
    suite = client_connecte.get(f"/contacts/{c['id']}/activites", params={"avant": fiche["activites_suivant"]}).json()
    assert [a["texte"] for a in suite["activites"]] == ["Note 3", "Note 2", "Note 1", "Note 0", None]
    assert suite["suivant"] is None
    assert client_connecte.get("/contacts/999/activites").status_code == 404


# --------------------------------------------------------------------------- pause et inscription manuelle

def test_pause_individuelle(client_connecte, session):
    inscrire_landing(client_connecte)
    c = session.exec(select(Contact)).one()
    r = client_connecte.post(f"/contacts/{c.id}/pause", json={"pause": True})
    assert r.status_code == 200
    assert r.json()["pause"] is True and r.json()["sequence"]["etat"] == "pause"
    session.refresh(c)
    assert c.pause is True
    r = client_connecte.post(f"/contacts/{c.id}/pause", json={"pause": False})
    assert r.json()["sequence"]["etat"] == "due"
    assert client_connecte.post("/contacts/999/pause", json={"pause": True}).status_code == 404


def test_inscription_manuelle_a_une_sequence(client_connecte, session, admin):
    c = client_connecte.post("/contacts", json={"type": "donateur", "prenom": "Prénom",
                                                "email": "prenom@exemple.test"}).json()
    assert client_connecte.get(f"/contacts/{c['id']}").json()["sequences_possibles"] == [
        "donateur-bienvenue", "donateur-pilote"]
    r = client_connecte.post(f"/contacts/{c['id']}/sequence", json={"sequence": "donateur-bienvenue"})
    assert r.status_code == 201
    assert set(r.json()) == CLES_ETAT_SEQUENCE and r.json()["sequence"] == "donateur-bienvenue"
    insc = session.exec(select(InscriptionSequence)).one()
    assert insc.inscrit_par_id == admin.id
    assert client_connecte.post(f"/contacts/{c['id']}/sequence",
                                json={"sequence": "donateur-bienvenue"}).status_code == 409
    assert client_connecte.post(f"/contacts/{c['id']}/sequence",
                                json={"sequence": "entreprise-entrante"}).status_code == 422
    assert client_connecte.get(f"/contacts/{c['id']}").json()["sequences_possibles"] == ["donateur-pilote"]

    sans_email = client_connecte.post("/contacts", json={"type": "donateur", "prenom": "Sans"}).json()
    assert client_connecte.post(f"/contacts/{sans_email['id']}/sequence",
                                json={"sequence": "donateur-bienvenue"}).status_code == 422
    parti = session.get(Contact, c["id"])
    parti.desinscrit_at = parti.cree_at
    session.add(parti)
    session.commit()
    assert client_connecte.post(f"/contacts/{c['id']}/sequence",
                                json={"sequence": "donateur-pilote"}).status_code == 409
    assert client_connecte.get(f"/contacts/{c['id']}").json()["sequences_possibles"] == []
    assert client_connecte.post("/contacts/999/sequence", json={"sequence": "donateur-pilote"}).status_code == 404


# --------------------------------------------------------------------------- import et export CSV

def _importer(client, contenu: str | bytes, nom="contacts.csv"):
    donnees = contenu.encode() if isinstance(contenu, str) else contenu
    return client.post("/contacts/import", files={"fichier": (nom, donnees, "text/csv")})


def test_import_csv_cree_et_complete(client_connecte, session):
    client_connecte.post("/contacts", json={"type": "donateur", "prenom": "Existant", "email": "existe@exemple.test"})
    csv = "﻿" + "\n".join([
        "prenom;nom;email;type;organisation;source",
        "Nouveau;Test;nouveau@exemple.test;;;landing",
        "Autre prénom;Complété;EXISTE@exemple.test;;;",
        "Entreprise;Test;dirigeant@exemple.test;entreprise;Entreprise Test 1;",
        "Invalide;Test;pas-une-adresse;;;",
        "Robot;Test;robot@exemple.test;robot;;",
        ";;;;;",
        ";Sans;;;;",
        "Existant;;existe@exemple.test;;;",
    ])
    r = _importer(client_connecte, csv)
    assert r.status_code == 200
    rep = r.json()
    assert (rep["crees"], rep["mis_a_jour"], rep["ignores"]) == (2, 1, 2)
    assert [e["ligne"] for e in rep["erreurs"]] == [5, 6, 8]
    assert all(e["raison"] for e in rep["erreurs"])

    existant = session.exec(select(Contact).where(Contact.email == "existe@exemple.test")).one()
    assert (existant.prenom, existant.nom, existant.source) == ("Existant", "Complété", "manuel")
    nouveau = session.exec(select(Contact).where(Contact.email == "nouveau@exemple.test")).one()
    assert (nouveau.type, nouveau.source, nouveau.consentement_at) == ("donateur", "import", None)
    dirigeant = session.exec(select(Contact).where(Contact.email == "dirigeant@exemple.test")).one()
    assert session.get(Organisation, dirigeant.organisation_id).nom == "Entreprise Test 1"
    affaire = session.exec(select(Affaire).where(Affaire.contact_id == dirigeant.id)).one()
    assert (affaire.pipeline, affaire.etape) == ("entreprises", "prospect")
    assert session.exec(select(Activite).where(Activite.type == "import")).all()

    virgules = _importer(client_connecte, "email,prenom\nvirgule@exemple.test,Virgule\n").json()
    assert virgules["crees"] == 1
    assert _importer(client_connecte, "nom;ville\nTest;Ville\n").status_code == 422


def test_import_csv_sans_sequence_automatique(client_connecte, session):
    _importer(client_connecte, "prenom;email;type\nUn;un@exemple.test;donateur\nDeux;deux@exemple.test;entreprise\n")
    assert len(session.exec(select(Contact)).all()) == 2
    assert session.exec(select(InscriptionSequence)).all() == []
    assert all(c.consentement_at is None for c in session.exec(select(Contact)))


def test_import_csv_trop_gros_413(client_connecte, session):
    gros = "prenom;email\n" + "x" * (2 * 1024 * 1024)
    assert _importer(client_connecte, gros).status_code == 413
    lignes = "prenom;email\n" + "".join(f"P{i};p{i}@exemple.test\n" for i in range(5001))
    assert _importer(client_connecte, lignes).status_code == 413
    assert session.exec(select(Contact)).all() == []


def test_export_csv_neutralise_les_formules(client_connecte, session, horloge):
    client_connecte.post("/contacts", json={
        "type": "entreprise", "prenom": "=SOMME(A1)", "nom": "+33", "poste": "-DRH", "ville": "@Ville",
        "email": "formule@exemple.test", "organisation_nom": "Entreprise Test 1"})
    inscrire_landing(client_connecte, email="landing@exemple.test", prenom="Prénom; Landing")
    r = client_connecte.get("/contacts/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert r.headers["content-disposition"] == 'attachment; filename="contacts-merci-2026-10-12.csv"'
    assert r.content.startswith(b"\xef\xbb\xbf")
    lignes = r.content.decode("utf-8-sig").splitlines()
    assert lignes[0] == ENTETE_CSV and len(lignes) == 3
    formule = next(x for x in lignes if "formule@" in x)
    assert formule.startswith("entreprise;'=SOMME(A1);'+33;formule@exemple.test;;'-DRH;Entreprise Test 1;'@Ville;")
    assert "manuel;;entreprises;prospect;;;;2026-10-12T08:00:00Z" in formule
    landing = next(x for x in lignes if "landing@" in x)
    assert landing.startswith('donateur;"Prénom; Landing";')
    assert "donateur-bienvenue;due;" in landing

    filtre = client_connecte.get("/contacts/export.csv", params={"type": "donateur"}).content.decode("utf-8-sig")
    assert len(filtre.splitlines()) == 2
