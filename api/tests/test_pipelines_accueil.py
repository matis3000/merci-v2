"""Pipelines, affaires, accueil, coque, réglages et équipe (sections 4.4, 4.5, 4.9)."""
from __future__ import annotations

import datetime as dt
import json

import pytest
from sqlmodel import select

from app import journal
from app.config import settings
from app.modeles import Activite, Affaire, InscriptionSequence, Membre, Reglage
from conftest import (
    CLES_AFFAIRE, CLES_CARTE, CLES_ETAT_SEQUENCE, CLES_MEMBRE, connecter, creer_affaire, creer_contact,
    creer_inscription, creer_membre, creer_organisation, inscrire_landing, iso,
)

# L'état juste après la capture : l'envoi immédiat est testé dans test_inscription.py.
pytestmark = pytest.mark.usefixtures("sans_envoi_immediat")

ETAPES_PARCOURS = ["attirer", "capturer", "suivre", "relancer", "convertir", "fideliser"]


# --------------------------------------------------------------------------- pipelines

def test_liste_des_pipelines(client_connecte):
    r = client_connecte.get("/pipelines")
    assert r.status_code == 200
    defs = r.json()
    assert [d["cle"] for d in defs] == ["donateurs", "entreprises", "associations"]
    assert defs[0] == {
        "cle": "donateurs", "nom": "Donateurs",
        "etapes": [{"cle": "inscrit", "nom": "Inscrit"}, {"cle": "bienvenue_envoyee", "nom": "Bienvenue envoyée"},
                   {"cle": "pilote_ouvert", "nom": "Pilote ouvert"}, {"cle": "compte_cree", "nom": "Compte créé"},
                   {"cle": "premier_don", "nom": "Premier don"}, {"cle": "fidele", "nom": "Fidèle"}],
        "etape_perdue": {"cle": "perdu", "nom": "Perdu"},
    }
    assert defs[2]["etape_perdue"] == {"cle": "perdue", "nom": "Perdue"}


def test_pipeline_base_vide(client_connecte):
    r = client_connecte.get("/pipelines/entreprises").json()
    assert set(r) == {"pipeline", "colonnes", "perdus", "compte_par_pipeline"}
    assert [c["etape"]["cle"] for c in r["colonnes"]] == [
        "prospect", "contacte", "a_repondu", "demo_planifiee", "demo_faite", "abonnement_signe", "salaries_actives"]
    assert all(c["cartes"] == [] for c in r["colonnes"])
    assert r["perdus"] == 0
    assert r["compte_par_pipeline"] == {"donateurs": 0, "entreprises": 0, "associations": 0}


def test_pipeline_colonnes_sans_perdu_et_compte_perdus(client_connecte, session, horloge):
    inscrire_landing(client_connecte, email="un@exemple.test", prenom="Prénom Un", source_detail="instagram")
    horloge.avancer(minutes=5)
    inscrire_landing(client_connecte, email="deux@exemple.test", prenom="Prénom Deux")
    horloge.avancer(minutes=5)
    inscrire_landing(client_connecte, email="trois@exemple.test", prenom="Prénom Trois")
    trois = session.exec(select(Affaire).order_by(Affaire.id.desc())).first()
    assert client_connecte.patch(f"/affaires/{trois.id}", json={"etape": "perdu"}).status_code == 200

    r = client_connecte.get("/pipelines/donateurs")
    assert r.status_code == 200
    rep = r.json()
    assert rep["pipeline"]["cle"] == "donateurs"
    assert "perdu" not in [c["etape"]["cle"] for c in rep["colonnes"]]
    assert len(rep["colonnes"]) == 6 and rep["perdus"] == 1
    assert rep["compte_par_pipeline"] == {"donateurs": 2, "entreprises": 0, "associations": 0}

    cartes = rep["colonnes"][0]["cartes"]
    assert [c["titre"] for c in cartes] == ["Prénom Deux", "Prénom Un"]  # etape_depuis décroissant
    carte = cartes[1]
    assert set(carte) == CLES_CARTE
    assert carte["cible"]["genre"] == "contact" and carte["sous_titre"] == "Via Instagram"
    assert carte["note"] is None
    assert set(carte["sequence"]) == CLES_ETAT_SEQUENCE
    assert carte["sequence"]["sequence"] == "donateur-bienvenue" and carte["sequence"]["etat"] == "due"

    q = client_connecte.get("/pipelines/donateurs", params={"q": "deux@"}).json()
    assert [c["titre"] for col in q["colonnes"] for c in col["cartes"]] == ["Prénom Deux"]


def test_carte_entreprise_et_organisation_sans_decideur(client_connecte, session):
    org = creer_organisation(session, "Entreprise Test 1", note=3)
    creer_affaire(session, "entreprises", "prospect", organisation_id=org.id)
    org2 = creer_organisation(session, "Entreprise Test 2", siren="000000002")
    c = creer_contact(session, type="entreprise", prenom="Prénom", nom="Test", poste="DRH",
                      organisation_id=org2.id, source="prospection")
    creer_affaire(session, "entreprises", "prospect", contact_id=c.id, organisation_id=org2.id)
    cartes = client_connecte.get("/pipelines/entreprises").json()["colonnes"][0]["cartes"]
    seule = next(x for x in cartes if x["cible"]["genre"] == "organisation")
    assert (seule["titre"], seule["sous_titre"], seule["note"]) == ("Entreprise Test 1", "Aucun décideur trouvé", 3)
    assert seule["cible"] == {"genre": "organisation", "id": org.id} and seule["sequence"] is None
    avec = next(x for x in cartes if x["cible"]["genre"] == "contact")
    assert (avec["titre"], avec["sous_titre"]) == ("Entreprise Test 2", "Prénom Test, DRH")


def test_pipeline_inconnu_404(client_connecte):
    assert client_connecte.get("/pipelines/inconnu").status_code == 404


def test_patch_etape_inconnue_422(client_connecte, session):
    inscrire_landing(client_connecte)
    affaire = session.exec(select(Affaire)).one()
    for corps in ({"etape": "inconnue"}, {"etape": "prospect"}, {"perdue_raison": "Pas intéressé"},
                  {"etape": "bienvenue_envoyee", "perdue_raison": "Pas intéressé"}):
        assert client_connecte.patch(f"/affaires/{affaire.id}", json=corps).status_code == 422, corps
    assert client_connecte.patch("/affaires/999", json={"etape": "inscrit"}).status_code == 404
    session.refresh(affaire)
    assert affaire.etape == "inscrit"


def test_patch_etape_manuel_journalise_et_arrete_la_sequence(client_connecte, session, admin, horloge):
    inscrire_landing(client_connecte)
    affaire = session.exec(select(Affaire)).one()
    insc = session.exec(select(InscriptionSequence)).one()
    horloge.avancer(minutes=3)
    r = client_connecte.patch(f"/affaires/{affaire.id}", json={"etape": "compte_cree"})
    assert r.status_code == 200
    rep = r.json()
    assert set(rep) == CLES_AFFAIRE
    assert rep["etape"] == {"cle": "compte_cree", "nom": "Compte créé"} and rep["etape_depuis"] == iso(horloge.t)
    assert [e["cle"] for e in rep["etapes_possibles"]][-1] == "perdu" and len(rep["etapes_possibles"]) == 7

    session.refresh(insc)
    assert (insc.statut, insc.raison_arret) == ("arretee", "etape_changee")
    changee = session.exec(select(Activite).where(Activite.type == "etape_changee")).one()
    assert changee.membre_id == admin.id
    assert json.loads(changee.donnees) == {"avant": "inscrit", "apres": "compte_cree"}
    assert session.exec(select(Activite).where(Activite.type == "sequence_arretee")).one()

    # Même étape : rien ne change.
    client_connecte.patch(f"/affaires/{affaire.id}", json={"etape": "compte_cree"})
    assert len(session.exec(select(Activite).where(Activite.type == "etape_changee")).all()) == 1


def test_patch_passage_en_perdu_raison_et_arret(client_connecte, session, admin):
    inscrire_landing(client_connecte)
    affaire = session.exec(select(Affaire)).one()
    r = client_connecte.patch(f"/affaires/{affaire.id}", json={
        "etape": "perdu", "perdue_raison": "Ne souhaite plus être contacté",
        "responsable_id": admin.id, "montant_mensuel": "12.50"})
    assert r.status_code == 200
    rep = r.json()
    assert rep["perdue_raison"] == "Ne souhaite plus être contacté"
    assert set(rep["responsable"]) == CLES_MEMBRE and rep["responsable"]["id"] == admin.id
    assert rep["montant_mensuel"] == "12.50"
    insc = session.exec(select(InscriptionSequence)).one()
    assert (insc.statut, insc.raison_arret) == ("arretee", "perdu")
    assert client_connecte.patch(f"/affaires/{affaire.id}", json={"responsable_id": 999}).status_code == 422
    r = client_connecte.patch(f"/affaires/{affaire.id}", json={"responsable_id": None, "montant_mensuel": None})
    assert r.json()["responsable"] is None and r.json()["montant_mensuel"] is None


# --------------------------------------------------------------------------- accueil

def test_accueil_base_vide_tout_a_zero(client_connecte):
    r = client_connecte.get("/accueil")
    assert r.status_code == 200
    rep = r.json()
    assert rep["parcours"]["etapes"] == [
        {"cle": "attirer", "nom": "Attirer", "info": "D'où ils viennent"},
        {"cle": "capturer", "nom": "Capturer", "info": "Inscrits, prospects"},
        {"cle": "suivre", "nom": "Suivre", "info": "Qualifier"},
        {"cle": "relancer", "nom": "Relancer", "info": "Séquences en cours"},
        {"cle": "convertir", "nom": "Convertir", "info": "Compte, démo, signature"},
        {"cle": "fideliser", "nom": "Fidéliser", "info": "Dons, salariés actifs"},
    ]
    vide = {e: {"n": 0, "detail": []} for e in ETAPES_PARCOURS}
    assert rep["parcours"]["publics"] == [
        {"pipeline": "donateurs", "nom": "Donateurs", "cases": vide},
        {"pipeline": "entreprises", "nom": "Entreprises", "cases": vide},
    ]
    assert rep["a_faire"] == [] and rep["arrives_landing"] == []
    assert rep["relances"] == {"partent_aujourdhui": 0, "en_cours": 0, "en_pause": 0, "en_echec": 0}


def _cases(client, pipeline):
    publics = client.get("/accueil").json()["parcours"]["publics"]
    return next(p for p in publics if p["pipeline"] == pipeline)["cases"]


def test_rattache_etapes_au_parcours(client_connecte, session):
    for etape in ("inscrit", "inscrit", "bienvenue_envoyee", "pilote_ouvert", "compte_cree", "premier_don",
                  "fidele", "perdu"):
        c = creer_contact(session, source_detail="instagram")
        creer_affaire(session, "donateurs", etape, contact_id=c.id)
    for etape in ("prospect", "contacte", "a_repondu", "demo_planifiee", "demo_faite", "salaries_actives", "perdu"):
        c = creer_contact(session, type="entreprise", source="prospection")
        creer_affaire(session, "entreprises", etape, contact_id=c.id)
    a = creer_contact(session, type="association")
    creer_affaire(session, "associations", "inscrite", contact_id=a.id)

    d = _cases(client_connecte, "donateurs")
    assert {k: v["n"] for k, v in d.items()} == {
        "attirer": 7, "capturer": 2, "suivre": 1, "relancer": 1, "convertir": 2, "fideliser": 1}
    assert d["capturer"]["detail"] == [{"libelle": "Inscrit", "n": 2}]
    assert d["convertir"]["detail"] == [{"libelle": "Compte créé", "n": 1}, {"libelle": "Premier don", "n": 1}]

    e = _cases(client_connecte, "entreprises")
    assert {k: v["n"] for k, v in e.items()} == {
        "attirer": 6, "capturer": 1, "suivre": 1, "relancer": 1, "convertir": 2, "fideliser": 1}
    assert e["relancer"]["detail"] == [{"libelle": "Contacté", "n": 1}]


def test_attirer_detaille_par_source(client_connecte, session):
    for detail in ("instagram", "instagram", "landing-v1-galet"):
        c = creer_contact(session, source_detail=detail)
        creer_affaire(session, "donateurs", "inscrit", contact_id=c.id)
    for source in ("prospection", "prospection", "landing"):
        c = creer_contact(session, type="entreprise", source=source)
        creer_affaire(session, "entreprises", "prospect", contact_id=c.id)
    org = creer_organisation(session, source="prospection")
    creer_affaire(session, "entreprises", "prospect", organisation_id=org.id)

    assert _cases(client_connecte, "donateurs")["attirer"] == {"n": 3, "detail": [
        {"libelle": "Instagram", "n": 2}, {"libelle": "Landing-v1-galet", "n": 1}]}
    assert _cases(client_connecte, "entreprises")["attirer"] == {"n": 4, "detail": [
        {"libelle": "Prospection", "n": 3}, {"libelle": "Landing", "n": 1}]}


def test_a_faire_reponse_puis_echec_puis_reste(client_connecte, session, horloge):
    org = creer_organisation(session, "Entreprise Test 1")

    def entreprise(prenom, etape):
        c = creer_contact(session, type="entreprise", prenom=prenom, nom="Test", poste="DRH",
                          organisation_id=org.id, source="prospection")
        creer_affaire(session, "entreprises", etape, contact_id=c.id, organisation_id=org.id)
        horloge.avancer(minutes=1)
        return c

    entreprise("Planifier", "a_repondu")
    entreprise("Preparer", "demo_planifiee")
    entreprise("Signer", "demo_faite")
    entreprise("Activer", "abonnement_signe")
    asso = creer_contact(session, type="association", prenom="Asso", nom="Test")
    creer_affaire(session, "associations", "inscrite", contact_id=asso.id)
    horloge.avancer(minutes=1)
    rebond = creer_contact(session, prenom="Rebond", nom="Test", email="rebond@exemple.test")
    creer_inscription(session, rebond.id, "donateur-bienvenue", statut="echec", raison_arret="rebond")
    horloge.avancer(minutes=1)
    essais = creer_contact(session, prenom="Essais", nom="Test", email="essais@exemple.test")
    creer_inscription(session, essais.id, "donateur-bienvenue", statut="echec", raison_arret="trois_essais")
    horloge.avancer(minutes=1)
    repondu = entreprise("Repondu", "a_repondu")
    journal.ajouter_activite(session, "linkedin_reponse", "Réponse reçue sur LinkedIn",
                             texte="Bonjour, volontiers.", contact_id=repondu.id)
    session.commit()

    items = client_connecte.get("/accueil").json()["a_faire"]
    assert [i["type"] for i in items] == [
        "reponse", "echec", "echec", "demo_a_planifier", "demo_a_preparer", "signature", "activer_salaries",
        "appeler_association"]
    rep = items[0]
    assert set(rep) == {"type", "titre", "sous_titre", "cible", "pastille", "ton", "bouton", "depuis"}
    assert (rep["titre"], rep["pastille"], rep["ton"], rep["bouton"]) == (
        "Repondu a répondu sur LinkedIn", "linkedin", "vert", "Lire la réponse")
    assert rep["cible"] == {"genre": "contact", "id": repondu.id}
    assert [i["titre"] for i in items[1:3]] == ["E-mail en rebond pour Rebond Test", "Envoi en échec pour Essais Test"]
    assert (items[1]["pastille"], items[1]["ton"], items[1]["bouton"]) == ("attention", "poudre", "Corriger")
    assert [i["titre"] for i in items[3:]] == [
        "Planifier la démo", "Préparer la démo", "Relancer pour la signature",
        "Envoyer le lien d'invitation des salariés", "Appeler l'association"]
    assert [i["pastille"] for i in items[3:]] == ["coche", "calendrier", "coche", "coche", "telephone"]
    assert all(i["bouton"] == "Ouvrir" and i["ton"] is None for i in items[3:])


def test_compteurs_relances(client_connecte, session, horloge):
    compteur = iter(range(100))

    def contact(**kw):
        return creer_contact(session, email=f"c{next(compteur)}@exemple.test", **kw)

    t = horloge.t
    creer_inscription(session, contact().id, "donateur-bienvenue", prochain_envoi_at=t)
    # 20 h UTC le 12/10 = 22 h à Paris : encore aujourd'hui, donc « part aujourd'hui ».
    creer_inscription(session, contact().id, "donateur-pilote", prochain_envoi_at=t.replace(hour=20))
    creer_inscription(session, contact().id, "donateur-pilote", prochain_envoi_at=t + dt.timedelta(days=3))
    creer_inscription(session, contact(pause=True).id, "donateur-pilote", prochain_envoi_at=t)
    creer_inscription(session, contact().id, "donateur-pilote", statut="echec", raison_arret="trois_essais")
    creer_inscription(session, contact().id, "donateur-bienvenue", statut="terminee", pas_courant=2)

    assert client_connecte.get("/accueil").json()["relances"] == {
        "partent_aujourdhui": 2, "en_cours": 1, "en_pause": 1, "en_echec": 1}

    r = session.get(Reglage, 1)
    r.relances_en_pause = True
    session.add(r)
    session.commit()
    assert client_connecte.get("/accueil").json()["relances"] == {
        "partent_aujourdhui": 0, "en_cours": 0, "en_pause": 4, "en_echec": 1}


def test_arrives_par_la_landing(client_connecte, session, horloge):
    for i in range(5):
        inscrire_landing(client_connecte, email=f"p{i}@exemple.test", prenom=f"Prénom {i}")
        horloge.avancer(minutes=1)
    inscrire_landing(client_connecte, "entreprise", email="e@exemple.test", prenom="Prénom E",
                     structure="Entreprise Test 1", source_detail="linkedin")
    creer_contact(session, prenom="Importé", email="import@exemple.test", source="import")
    arrives = client_connecte.get("/accueil").json()["arrives_landing"]
    assert [a["nom_affiche"] for a in arrives] == ["Prénom E", "Prénom 4", "Prénom 3", "Prénom 2"]
    assert set(arrives[0]) == {"cible", "nom_affiche", "type", "organisation_nom", "source_detail", "cree_at"}
    assert (arrives[0]["type"], arrives[0]["organisation_nom"], arrives[0]["source_detail"]) == (
        "entreprise", "Entreprise Test 1", "linkedin")


# --------------------------------------------------------------------------- coque

def test_coque_base_vide(client_connecte, horloge):
    assert client_connecte.get("/coque").json() == {
        "aujourdhui": "2026-10-12", "nb_contacts": 0, "nb_sequences_en_cours": 0, "relances_en_pause": False,
        "creneau": {"jours": [1, 2, 3, 4, 5], "debut": 9, "fin": 18},
        "linkedin": {"fournisseur": "factice", "etat": "non_configure"}, "nb_echecs": 0,
    }


def test_coque_compteurs(client_connecte, session, horloge):
    inscrire_landing(client_connecte)
    org = creer_organisation(session)
    creer_affaire(session, "entreprises", "prospect", organisation_id=org.id)
    c = creer_contact(session, email="echec@exemple.test")
    creer_inscription(session, c.id, "donateur-bienvenue", statut="echec", raison_arret="rebond")
    r = session.get(Reglage, 1)
    r.linkedin_etat = "a_reconnecter"
    session.add(r)
    session.commit()
    horloge.avancer(hours=15)  # 23 h UTC = 1 h du matin à Paris, le 13
    rep = client_connecte.get("/coque").json()
    assert (rep["aujourdhui"], rep["nb_contacts"], rep["nb_sequences_en_cours"], rep["nb_echecs"]) == (
        "2026-10-13", 3, 1, 1)
    assert rep["linkedin"] == {"fournisseur": "factice", "etat": "a_reconnecter"}


# --------------------------------------------------------------------------- réglages et équipe

def test_reglages_base_vide(client_connecte, admin):
    rep = client_connecte.get("/reglages").json()
    assert rep == {
        "relances_en_pause": False,
        "creneau": {"jours": [1, 2, 3, 4, 5], "debut": 9, "fin": 18, "fuseau": "Europe/Paris"},
        "expediteur": {"nom": "MERCI", "email": "bonjour@exemple.test"}, "reponse_a": None,
        "lien_rdv": None, "lien_creation_compte": None, "pilote_ouvert_at": None,
        "connexions": {
            "landing": {"derniere_inscription_at": None,
                        "origines": ["http://127.0.0.1:5500", "http://localhost:5500"]},
            "email": {"fournisseur": "console", "etat": "non_configure", "derniere_erreur_at": None},
            "linkedin": {"fournisseur": "factice", "etat": "non_configure"},
            "app_merci": {"cle_configuree": True, "cle_masquee": "••••-app"},
        },
        "equipe": [{"id": admin.id, "email": "admin@exemple.test", "prenom": "Admin Test", "role": "admin",
                    "actif": True}],
        "hubspot_etapes": {"donateurs": {}, "entreprises": {}, "associations": {}},
    }


def test_reglages_derniere_inscription_landing(client_connecte, horloge):
    inscrire_landing(client_connecte)
    rep = client_connecte.get("/reglages").json()
    assert rep["connexions"]["landing"]["derniere_inscription_at"] == iso(horloge.t)


def test_reglages_pause_generale_par_l_equipe(client, session, membre):
    connecter(client, membre)
    r = client.patch("/reglages", json={"relances_en_pause": True, "lien_rdv": "https://exemple.test/rdv"})
    assert r.status_code == 200
    assert r.json()["relances_en_pause"] is True and r.json()["lien_rdv"] == "https://exemple.test/rdv"
    assert client.get("/coque").json()["relances_en_pause"] is True
    for corps in ({"creneau": {"jours": [1], "debut": 9, "fin": 18}},
                  {"expediteur": {"nom": "MERCI", "email": "autre@exemple.test"}},
                  {"reponse_a": "equipe@exemple.test"}):
        assert client.patch("/reglages", json=corps).status_code == 403, corps
    assert client.patch("/reglages", json={"lien_rdv": ""}).json()["lien_rdv"] is None


def test_reglages_creneau_et_expediteur_admin(client_connecte, monkeypatch):
    for creneau in ({"jours": [1], "debut": 18, "fin": 9}, {"jours": [1], "debut": 9, "fin": 9},
                    {"jours": [0], "debut": 9, "fin": 18}, {"jours": [8], "debut": 9, "fin": 18},
                    {"jours": [], "debut": 9, "fin": 18}, {"jours": [1], "debut": 9, "fin": 25}):
        assert client_connecte.patch("/reglages", json={"creneau": creneau}).status_code == 422, creneau
    r = client_connecte.patch("/reglages", json={
        "creneau": {"jours": [5, 1, 1], "debut": 0, "fin": 24},
        "expediteur": {"nom": "Équipe MERCI", "email": "Equipe@Exemple.test"},
        "reponse_a": "reponses@exemple.test"})
    assert r.status_code == 200
    rep = r.json()
    assert rep["creneau"] == {"jours": [1, 5], "debut": 0, "fin": 24, "fuseau": "Europe/Paris"}
    assert rep["expediteur"] == {"nom": "Équipe MERCI", "email": "equipe@exemple.test"}
    assert rep["reponse_a"] == "reponses@exemple.test"
    assert client_connecte.patch("/reglages", json={"reponse_a": "pas-une-adresse"}).status_code == 422

    monkeypatch.setattr(settings, "mode", "production")
    assert client_connecte.patch("/reglages", json={"lien_rdv": "http://exemple.test/rdv"}).status_code == 422
    assert client_connecte.patch("/reglages", json={"lien_rdv": "https://exemple.test/rdv"}).status_code == 200


def test_equipe_invitation_par_l_admin(client_connecte, fournisseurs_factices):
    r = client_connecte.post("/equipe", json={"email": "Nouveau@Exemple.test", "prenom": "Nouveau", "role": "equipe"})
    assert r.status_code == 201
    assert set(r.json()) == CLES_MEMBRE and r.json()["email"] == "nouveau@exemple.test"
    envois = [json.loads(p.read_text()) for p in fournisseurs_factices.emails()]
    assert [e["a"] for e in envois] == ["nouveau@exemple.test"]
    assert "/connexion/verifier?jeton=" in envois[0]["texte"]
    assert client_connecte.post("/equipe", json={"email": "nouveau@exemple.test", "prenom": "N",
                                                 "role": "equipe"}).status_code == 409
    assert client_connecte.post("/equipe", json={"email": "x@exemple.test", "prenom": "X",
                                                 "role": "chef"}).status_code == 422
    assert len(client_connecte.get("/reglages").json()["equipe"]) == 2


def test_equipe_dernier_admin_protege(client_connecte, session, admin):
    for corps in ({"role": "equipe"}, {"actif": False}):
        assert client_connecte.patch(f"/equipe/{admin.id}", json=corps).status_code == 409, corps
    assert client_connecte.patch("/equipe/999", json={"prenom": "X"}).status_code == 404
    autre = creer_membre(session, "second@exemple.test", role="admin")
    r = client_connecte.patch(f"/equipe/{autre.id}", json={"prenom": "Second", "actif": False})
    assert r.status_code == 200 and r.json()["actif"] is False and r.json()["prenom"] == "Second"
    assert client_connecte.patch(f"/equipe/{admin.id}", json={"role": "equipe"}).status_code == 409
    client_connecte.patch(f"/equipe/{autre.id}", json={"actif": True})
    assert client_connecte.patch(f"/equipe/{admin.id}", json={"role": "equipe"}).json()["role"] == "equipe"
    session.expire_all()
    assert session.get(Membre, admin.id).role == "equipe"
