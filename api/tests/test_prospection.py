"""Prospection : registre (transport simulé), décideurs LinkedIn (factice injecté), note, affaires,
séquence, passages et route `/prospection` (sections 4.8, 4.11, 7)."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import httpx
import pytest
from sqlmodel import select

from app import verrou
from app.config import settings
from app.fournisseurs.base import PersonneLinkedIn, ProfilLinkedIn
from app.fournisseurs.linkedin_factice import FauxLinkedInProvider
from app.modeles import Activite, Affaire, Contact, InscriptionSequence, Organisation, PassageProspection
from app.prospection import moteur, registre
from conftest import creer_organisation, regler, utiliser_linkedin

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "registre_67_page1.json").read_text())
CLES_PROSPECTION = {"cible", "dernier_passage", "en_cours", "invitations_aujourdhui", "a_rechercher", "entreprises"}
CLES_PASSAGE = {"id", "declencheur", "statut", "debut_at", "fin_at", "entreprises_vues", "nouvelles", "decideurs",
                "en_sequence", "erreur"}
CLES_ENTREPRISE = {"organisation_id", "nom", "ville", "effectif_libelle", "naf_libelle", "decideur", "note",
                   "suite", "suite_libelle"}


@pytest.fixture()
def requetes_registre(monkeypatch) -> list[httpx.Request]:
    """Le registre répond la page fictive ; aucune attente de cadence pendant les tests."""
    recues: list[httpx.Request] = []

    def repondre(request: httpx.Request) -> httpx.Response:
        recues.append(request)
        return httpx.Response(200, json=FIXTURE)

    monkeypatch.setattr(moteur, "TRANSPORT_REGISTRE", httpx.MockTransport(repondre))
    monkeypatch.setattr(moteur, "ATTENDRE", lambda secondes: None)
    return recues


def _personne(n: int, poste: str = "DRH", entreprise: str = "ENTREPRISE TEST 1") -> PersonneLinkedIn:
    return PersonneLinkedIn(provider_id=f"factice-personne-{n}", prenom=f"Prénom{n}", nom="Test", poste=poste,
                            entreprise=entreprise, url=f"https://www.linkedin.com/in/prenom{n}-test/")


def _linkedin(tmp_path, **kw) -> FauxLinkedInProvider:
    f = FauxLinkedInProvider(dossier=tmp_path / "outbox-linkedin", **kw)
    utiliser_linkedin(f)
    return f


def _lancer(client) -> int:
    r = client.post("/prospection/lancer")
    assert r.status_code == 202, r.text
    assert set(r.json()) == {"passage_id"}
    return r.json()["passage_id"]


def _passage(session, ident) -> PassageProspection:
    session.expire_all()
    return session.get(PassageProspection, ident)


def _orgs(session) -> dict[str, Organisation]:
    session.expire_all()
    return {o.siren: o for o in session.exec(select(Organisation))}


# --------------------------------------------------------------------------- registre

def test_registre_parametres_67_et_tranches_50_plus(client_connecte, session, horloge, requetes_registre):
    ident = _lancer(client_connecte)
    [req] = requetes_registre
    assert (req.url.scheme, req.url.host, req.url.path) == ("https", "recherche-entreprises.api.gouv.fr", "/search")
    p = req.url.params
    assert p["departement"] == "67"
    assert p["tranche_effectif_salarie"] == "21,22,31,32,41,42,51,52,53"
    assert (p["etat_administratif"], p["per_page"], p["page"]) == ("A", "25", "1")
    passage = _passage(session, ident)
    assert (passage.statut, passage.entreprises_vues, passage.nouvelles) == ("fini", 3, 3)


def test_registre_exclut_administration_publique(client_connecte, session, horloge, requetes_registre):
    _lancer(client_connecte)
    assert "900000003" not in _orgs(session)


def test_registre_exclut_sans_etablissement_dans_la_zone(client_connecte, session, horloge, requetes_registre):
    _lancer(client_connecte)
    orgs = _orgs(session)
    assert "900000004" not in orgs  # seul établissement du 67 fermé
    o5 = orgs["900000005"]          # siège à Paris, établissement actif à Haguenau
    assert (o5.ville, o5.code_postal, o5.departement) == ("Haguenau", "67500", "67")
    o1 = orgs["900000001"]
    assert (o1.type, o1.source, o1.nom, o1.tranche_effectif, o1.naf_code) == (
        "entreprise", "prospection", "ENTREPRISE TEST 1", "32", "62.01Z")


def test_registre_reprise_sur_429():
    appels, attentes = [], []

    def repondre(request):
        appels.append(request)
        if len(appels) == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json=FIXTURE)

    trouvees = registre.chercher_entreprises(["67"], ["32"], 1, transport=httpx.MockTransport(repondre),
                                             sleep=attentes.append)
    assert len(appels) == 2 and 3.0 in attentes
    assert [t.siren for t in trouvees] == ["900000001", "900000002", "900000003", "900000005"]
    # 429 persistant : erreur claire, pas de boucle.
    with pytest.raises(registre.ErreurRegistre):
        registre.chercher_entreprises(["67"], ["32"], 1, sleep=lambda s: None,
                                      transport=httpx.MockTransport(lambda r: httpx.Response(429)))


def test_doublon_siren_non_recree(client_connecte, session, horloge, requetes_registre):
    _lancer(client_connecte)
    horloge.avancer(minutes=5)
    deuxieme = _passage(session, _lancer(client_connecte))
    assert (deuxieme.entreprises_vues, deuxieme.nouvelles) == (3, 0)
    assert len(_orgs(session)) == 3


# --------------------------------------------------------------------------- décideurs, note, affaires, séquence

def test_deux_decideurs_au_plus(client_connecte, session, horloge, requetes_registre, tmp_path):
    f = _linkedin(tmp_path, personnes={"ENTREPRISE TEST 1": [_personne(1), _personne(2, "RH"), _personne(3, "RSE")]})
    ident = _lancer(client_connecte)
    session.expire_all()
    contacts = list(session.exec(select(Contact)))
    assert sorted(c.linkedin_provider_id for c in contacts) == ["factice-personne-1", "factice-personne-2"]
    c = next(c for c in contacts if c.linkedin_provider_id == "factice-personne-1")
    assert (c.type, c.source, c.source_detail, c.poste, c.prenom) == (
        "entreprise", "prospection", "Registre + LinkedIn", "DRH", "Prénom1")
    assert c.linkedin_url == "https://www.linkedin.com/in/prenom1-test/"
    assert c.organisation_id == _orgs(session)["900000001"].id
    assert _passage(session, ident).decideurs == 2
    assert ("chercher", "ENTREPRISE TEST 1") in [a[:2] for a in f.appels]
    assert all(a[3] == 2 for a in f.appels if a[0] == "chercher")  # limite = 2


def test_intitule_hors_cible_ecarte(client_connecte, session, horloge, requetes_registre, tmp_path):
    _linkedin(tmp_path, personnes={"ENTREPRISE TEST 1": [_personne(1, "Directeur commercial"),
                                                         _personne(2, "Responsable des ressources humaines")]})
    _lancer(client_connecte)
    session.expire_all()
    assert list(session.exec(select(Contact))) == []
    o1 = _orgs(session)["900000001"]
    assert o1.recherche_linkedin_at == horloge.t and o1.note == 3


def test_note_6_entre_en_sequence_note_5_reste_au_pipeline(client_connecte, session, horloge, requetes_registre,
                                                           tmp_path):
    _linkedin(tmp_path, personnes={
        "ENTREPRISE TEST 2": [_personne(2, "DRH", "ENTREPRISE TEST 2")],          # 50 à 99 : 4 + 2 = 6
        "ENTREPRISE TEST 5": [_personne(5, "People Manager", "ENTREPRISE TEST 5")],  # 10 à 19 : 4
    }, profils={"factice-personne-5": ProfilLinkedIn(
        provider_id="factice-personne-5", prenom="Prénom5", nom="Test", poste="People Manager", entreprise=None,
        url=None, posts_recents=[(horloge.t - dt.timedelta(days=40), "Notre démarche RSE")])})
    ident = _lancer(client_connecte)
    orgs = _orgs(session)
    assert (orgs["900000002"].note, orgs["900000005"].note) == (6, 4)
    assert json.loads(orgs["900000002"].raisons_note) == ["Décideur DRH trouvé +4", "50 à 249 salariés +2"]
    inscrits = {i.contact_id for i in session.exec(select(InscriptionSequence))}
    c2 = session.exec(select(Contact).where(Contact.linkedin_provider_id == "factice-personne-2")).one()
    c5 = session.exec(select(Contact).where(Contact.linkedin_provider_id == "factice-personne-5")).one()
    assert inscrits == {c2.id}
    insc = session.exec(select(InscriptionSequence)).one()
    assert (insc.sequence, insc.statut, insc.pas_courant, insc.prochain_envoi_at) == (
        "entreprise-prospection", "active", 1, horloge.t)
    affaires = {a.contact_id: a for a in session.exec(select(Affaire).where(Affaire.contact_id.is_not(None)))}
    assert affaires[c5.id].etape == "prospect" and affaires[c5.id].pipeline == "entreprises"
    assert affaires[c2.id].organisation_id == orgs["900000002"].id
    assert _passage(session, ident).en_sequence == 1
    # Le seuil est lu dans la cible.
    regler(session, prospection_seuil=4)
    horloge.avancer(minutes=5)
    assert _passage(session, _lancer(client_connecte)).en_sequence == 1
    session.expire_all()
    assert {i.contact_id for i in session.exec(select(InscriptionSequence))} == {c2.id, c5.id}


def test_sans_decideur_affaire_organisation_seule_sans_sequence(client_connecte, session, horloge,
                                                                 requetes_registre):
    _lancer(client_connecte)
    o1 = _orgs(session)["900000001"]
    [affaire] = session.exec(select(Affaire).where(Affaire.organisation_id == o1.id)).all()
    assert (affaire.pipeline, affaire.etape, affaire.contact_id) == ("entreprises", "prospect", None)
    assert session.exec(select(InscriptionSequence)).all() == []
    assert (o1.note, json.loads(o1.raisons_note)) == (3, ["Aucun décideur RH ou RSE trouvé", "250 salariés et plus +3"])
    lignes = client_connecte.get("/contacts").json()["lignes"]
    ligne = next(l for l in lignes if l["genre"] == "organisation" and l["id"] == o1.id)
    assert ligne["source_detail"] == "Registre seul" and ligne["note"] == 3
    activite = session.exec(select(Activite).where(Activite.organisation_id == o1.id,
                                                   Activite.type == "prospection_trouve")).one()
    assert activite.texte == ("Registre des entreprises (Bas-Rhin, 250 à 499 salariés). "
                              "Aucun décideur RH ou RSE trouvé. Note 3/10.")


def test_post_rse_recent_donne_le_signal_et_10_sur_10(client_connecte, session, horloge, requetes_registre,
                                                       tmp_path):
    _linkedin(tmp_path, personnes={"ENTREPRISE TEST 1": [_personne(1, "Responsable RSE")]},
              profils={"factice-personne-1": ProfilLinkedIn(
                  provider_id="factice-personne-1", prenom="Prénom1", nom="Test", poste="Responsable RSE",
                  entreprise=None, url=None,
                  posts_recents=[(horloge.t - dt.timedelta(days=3), "Notre démarche RSE avance bien")])})
    _lancer(client_connecte)
    o1 = _orgs(session)["900000001"]
    assert (o1.note, o1.signal_rse_libelle, o1.signal_rse_at) == (10, "Post RSE", horloge.t - dt.timedelta(days=3))
    c = session.exec(select(Contact)).one()
    activite = session.exec(select(Activite).where(Activite.contact_id == c.id,
                                                   Activite.type == "prospection_trouve")).one()
    assert activite.titre == "Trouvé par la prospection"
    assert activite.texte == ("Registre des entreprises (Bas-Rhin, 250 à 499 salariés), puis profil LinkedIn "
                              "« Responsable RSE ». Note 10/10.")


def test_linkedin_a_reconnecter_saute_les_decideurs(client_connecte, session, horloge, requetes_registre, tmp_path):
    f = _linkedin(tmp_path, personnes={"ENTREPRISE TEST 1": [_personne(1)]})
    regler(session, linkedin_etat="a_reconnecter")
    ident = _lancer(client_connecte)
    assert f.appels == [] and _passage(session, ident).statut == "fini"
    assert _orgs(session)["900000001"].recherche_linkedin_at is None


# --------------------------------------------------------------------------- passages, verrou, cron

def test_passage_cron_idempotent_sur_la_journee(client, session, horloge, requetes_registre):
    entetes = {"X-Cron-Secret": settings.cron_secret}
    r1 = client.post("/cron/prospection", headers=entetes)
    assert r1.status_code == 202
    ident = r1.json()["passage_id"]
    horloge.avancer(hours=3)
    r2 = client.post("/cron/prospection", headers=entetes)
    assert (r2.status_code, r2.json()) == (200, {"statut": "deja_fait", "passage_id": ident})
    assert len(requetes_registre) == 1
    passage = _passage(session, ident)
    assert (passage.cle, passage.declencheur, passage.statut) == ("cron:2026-10-12", "cron", "fini")
    horloge.t = dt.datetime(2026, 10, 12, 22, 30)  # 0 h 30 à Paris le 13 : nouveau jour
    r3 = client.post("/cron/prospection", headers=entetes)
    assert r3.status_code == 202 and r3.json()["passage_id"] != ident


def test_lancer_maintenant_409_si_en_cours(client_connecte, session, horloge, requetes_registre):
    assert verrou.prendre(session, "prospection", dt.timedelta(minutes=60))
    r = client_connecte.post("/prospection/lancer")
    assert r.status_code == 409 and "cours" in r.json()["detail"]
    r = client_connecte.post("/cron/prospection", headers={"X-Cron-Secret": settings.cron_secret})
    assert r.status_code == 409
    assert requetes_registre == []
    assert client_connecte.get("/prospection").json()["en_cours"] is True
    horloge.avancer(minutes=61)  # verrou expiré : repris
    assert client_connecte.post("/prospection/lancer").status_code == 202


def test_recherches_linkedin_limitees_par_passage(client_connecte, session, horloge, monkeypatch, tmp_path):
    monkeypatch.setattr(moteur, "TRANSPORT_REGISTRE",
                        httpx.MockTransport(lambda r: httpx.Response(200, json={"results": [], "total_pages": 1})))
    monkeypatch.setattr(moteur, "ATTENDRE", lambda s: None)
    for n in range(45):
        creer_organisation(session, f"Entreprise Test {n + 1}", siren=f"{n + 1:09d}",
                           tranche_effectif="53" if n == 44 else "21")
    f = _linkedin(tmp_path)
    _lancer(client_connecte)
    recherches = [a[1] for a in f.appels if a[0] == "chercher"]
    assert len(recherches) == moteur.RECHERCHES_LINKEDIN_PAR_PASSAGE == 40
    assert recherches[0] == "Entreprise Test 45"  # effectif décroissant
    assert client_connecte.get("/prospection").json()["a_rechercher"] == 5


def test_cron_prospection_secret_invalide_401(client, requetes_registre):
    assert client.post("/cron/prospection").status_code == 401
    assert client.post("/cron/prospection", headers={"X-Cron-Secret": "mauvais"}).status_code == 401
    assert requetes_registre == []


def test_offres_ignorees_sans_cle_france_travail(client_connecte, session, horloge, requetes_registre, monkeypatch):
    monkeypatch.setattr(settings, "france_travail_client_id", "")
    monkeypatch.setattr(settings, "france_travail_client_secret", "")
    appels = []
    monkeypatch.setattr(moteur, "TRANSPORT_OFFRES", httpx.MockTransport(lambda r: appels.append(r)))
    ident = _lancer(client_connecte)
    assert appels == [] and _passage(session, ident).statut == "fini"


def test_offre_rse_rapprochee_par_nom(client_connecte, session, horloge, requetes_registre, monkeypatch):
    monkeypatch.setattr(settings, "france_travail_client_id", "id-test")
    monkeypatch.setattr(settings, "france_travail_client_secret", "secret-test")

    def repondre(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"access_token": "jeton-test"})
        if request.url.params["motsCles"] == "QVT":
            return httpx.Response(200, json={"resultats": [
                {"intitule": "Chargé QVT (H/F)", "dateCreation": "2026-10-05T09:00:00.000Z",
                 "entreprise": {"nom": "Entreprise test 2"}}]})
        return httpx.Response(204)

    monkeypatch.setattr(moteur, "TRANSPORT_OFFRES", httpx.MockTransport(repondre))
    _lancer(client_connecte)
    o2 = _orgs(session)["900000002"]
    assert (o2.signal_rse_libelle, o2.signal_rse_at) == ("Offre d'emploi QVT", dt.datetime(2026, 10, 5))
    assert o2.note == 5 and "Offre d'emploi QVT ce mois +3" in json.loads(o2.raisons_note)


def test_erreur_registre_passage_en_erreur_sans_secret(client_connecte, session, horloge, monkeypatch):
    monkeypatch.setattr(moteur, "TRANSPORT_REGISTRE", httpx.MockTransport(lambda r: httpx.Response(503)))
    monkeypatch.setattr(moteur, "ATTENDRE", lambda s: None)
    passage = _passage(session, _lancer(client_connecte))
    assert (passage.statut, passage.erreur) == ("erreur", "Registre : HTTP 503")
    assert passage.fin_at == horloge.t
    horloge.avancer(minutes=1)
    assert client_connecte.post("/prospection/lancer").status_code == 202  # verrou relâché


# --------------------------------------------------------------------------- GET /prospection, cible

def test_prospection_base_vide(client_connecte):
    r = client_connecte.get("/prospection")
    assert r.status_code == 200
    corps = r.json()
    assert set(corps) == CLES_PROSPECTION
    assert corps["cible"] == {"departements": ["67"], "effectif_min": 50,
                              "postes": ["DRH", "RH", "RSE", "QVT", "People"], "plafond_jour": 20, "seuil": 6}
    assert (corps["dernier_passage"], corps["en_cours"], corps["invitations_aujourdhui"], corps["a_rechercher"],
            corps["entreprises"]) == (None, False, 0, 0, [])


def test_prospection_apres_passage_forme_et_suites(client_connecte, session, horloge, requetes_registre, tmp_path):
    _linkedin(tmp_path, personnes={
        "ENTREPRISE TEST 1": [_personne(1)],
        "ENTREPRISE TEST 2": [_personne(2, "DRH", "ENTREPRISE TEST 2")],
        "ENTREPRISE TEST 5": [_personne(5, "RH", "ENTREPRISE TEST 5")],
    })
    regler(session, prospection_plafond_jour=1)
    _lancer(client_connecte)
    corps = client_connecte.get("/prospection").json()
    passage = corps["dernier_passage"]
    assert set(passage) == CLES_PASSAGE
    assert (passage["declencheur"], passage["statut"], passage["entreprises_vues"], passage["nouvelles"],
            passage["decideurs"], passage["en_sequence"]) == ("manuel", "fini", 3, 3, 3, 2)
    assert passage["debut_at"].endswith("Z")
    lignes = corps["entreprises"]
    assert all(set(e) == CLES_ENTREPRISE for e in lignes)
    assert [e["nom"] for e in lignes] == ["ENTREPRISE TEST 1", "ENTREPRISE TEST 2", "ENTREPRISE TEST 5"]
    e1, e2, e5 = lignes
    assert (e1["note"], e1["effectif_libelle"], e1["ville"]) == (7, "250 à 499 salariés", "Strasbourg")
    assert e1["decideur"]["nom"] == "Prénom1 Test" and e1["decideur"]["poste"] == "DRH"
    assert (e1["suite"], e1["suite_libelle"]) == ("en_sequence", "Invitation au prochain créneau")
    assert (e2["suite"], e2["suite_libelle"]) == ("file_plafond", "File d'attente (plafond du jour)")
    assert (e5["note"], e5["suite"], e5["suite_libelle"]) == (4, "a_traiter", "À traiter à la main")


def test_put_cible(client_connecte, session):
    cible = {"departements": ["67", "68"], "effectif_min": 100, "postes": ["DRH", "RSE"], "plafond_jour": 15,
             "seuil": 7}
    r = client_connecte.put("/prospection/cible", json=cible)
    assert (r.status_code, r.json()) == (200, cible)
    assert client_connecte.get("/prospection").json()["cible"] == cible
    for faux in ({**cible, "departements": []}, {**cible, "departements": ["67"] * 6},
                 {**cible, "effectif_min": 75}, {**cible, "postes": []}, {**cible, "plafond_jour": 81},
                 {**cible, "seuil": 0}, {**cible, "departements": ["Bas-Rhin"]}):
        assert client_connecte.put("/prospection/cible", json=faux).status_code == 422
