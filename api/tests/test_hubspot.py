"""Lot L8 : synchro sens unique CRM vers HubSpot.

Aucun réseau : un faux HubSpot en mémoire répond derrière `httpx.MockTransport`. Il ne reconnaît
que les points d'accès confirmés par la documentation officielle (voir `crm_hubspot.py`).
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal

import httpx
import pytest
from sqlmodel import select

from app import fournisseurs, securite
from app.config import settings
from app.fournisseurs.crm_factice import FauxCrmProvider
from app.fournisseurs.crm_hubspot import HubspotCrmProvider
from app.main import app
from app.modeles import Affaire, Contact, SynchroHubspot
from app.services import synchro_hubspot as synchro
from conftest import (
    connecter, creer_affaire, creer_contact, creer_membre, creer_organisation, inscrire_landing, tick,
)

JETON = "pat-na1-jeton-secret-de-test-0000"
ETAPES_HS = [
    {"id": "etape-hs-2", "label": "Étape HubSpot 2", "displayOrder": 1},
    {"id": "etape-hs-1", "label": "Étape HubSpot 1", "displayOrder": 0},
]


class FauxHubspot:
    """Faux serveur HubSpot : enregistre les requêtes, attribue des identifiants, peut échouer."""

    def __init__(self):
        self.requetes: list[httpx.Request] = []
        self.objets: dict[str, dict[str, dict]] = {"contacts": {}, "companies": {}, "deals": {}}
        self.groupes: dict[str, set[str]] = {"contacts": set(), "companies": set(), "deals": set()}
        self.proprietes: dict[str, set[str]] = {"contacts": {"email"}, "companies": {"name"}, "deals": {"dealname"}}
        self.associations: set[tuple[str, str, str, str]] = set()
        self.pannes: list[tuple[int, dict]] = []   # réponses forcées, une par requête, dans l'ordre
        self.panne_permanente: tuple[int, dict] | None = None
        self._n = 100

    def _id(self) -> str:
        self._n += 1
        return str(self._n)

    def fournisseur(self) -> HubspotCrmProvider:
        return HubspotCrmProvider(JETON, transport=httpx.MockTransport(self.repondre))

    def chemins(self, methode: str | None = None) -> list[str]:
        return [f"{r.method} {r.url.path}" for r in self.requetes if methode in (None, r.method)]

    def corps(self, motif: str) -> list[dict]:
        return [json.loads(r.content) for r in self.requetes if re.search(motif, f"{r.method} {r.url.path}")]

    def contact(self, email: str) -> dict:
        return next(o for o in self.objets["contacts"].values() if o.get("email") == email)

    def repondre(self, req: httpx.Request) -> httpx.Response:
        self.requetes.append(req)
        assert req.headers["Authorization"] == f"Bearer {JETON}"
        if self.panne_permanente:
            return httpx.Response(self.panne_permanente[0], json=self.panne_permanente[1])
        if self.pannes:
            code, corps = self.pannes.pop(0)
            return httpx.Response(code, json=corps)
        m, p = req.method, req.url.path
        corps = json.loads(req.content) if req.content else {}
        if g := re.fullmatch(r"/crm/v3/properties/(\w+)/groups", p):
            if m == "GET":
                return httpx.Response(200, json={"results": [{"name": n, "label": n} for n in self.groupes[g[1]]]})
            self.groupes[g[1]].add(corps["name"])
            return httpx.Response(201, json=corps)
        if g := re.fullmatch(r"/crm/v3/properties/(\w+)", p):
            if m == "GET":
                return httpx.Response(200, json={"results": [{"name": n} for n in self.proprietes[g[1]]]})
            assert {"name", "label", "type", "fieldType", "groupName"} <= set(corps)
            self.proprietes[g[1]].add(corps["name"])
            return httpx.Response(201, json=corps)
        if p == "/crm/v3/objects/contacts/batch/upsert":
            [entree] = corps["inputs"]
            assert entree["idProperty"] == "email"
            existant = next((i for i, o in self.objets["contacts"].items() if o.get("email") == entree["id"]), None)
            ident = existant or self._id()
            self.objets["contacts"].setdefault(ident, {}).update({**entree["properties"], "email": entree["id"]})
            return httpx.Response(200, json={"status": "COMPLETE", "startedAt": "x", "completedAt": "x", "results": [
                {"id": ident, "new": existant is None, "properties": {}, "archived": False,
                 "createdAt": "x", "updatedAt": "x"}]})
        if g := re.fullmatch(r"/crm/v3/objects/(contacts|companies|deals)", p):
            assert m == "POST" and corps["associations"] == []
            ident = self._id()
            self.objets[g[1]][ident] = dict(corps["properties"])
            return httpx.Response(201, json={"id": ident, "properties": corps["properties"]})
        if g := re.fullmatch(r"/crm/v3/objects/(contacts|companies|deals)/(\w+)", p):
            assert m == "PATCH"
            if g[2] not in self.objets[g[1]]:
                return httpx.Response(404, json={"message": "introuvable"})
            self.objets[g[1]][g[2]].update(corps["properties"])
            return httpx.Response(200, json={"id": g[2], "properties": {}})
        if g := re.fullmatch(r"/crm/v4/objects/([\d-]+)/(\w+)/associations/default/([\d-]+)/(\w+)", p):
            assert m == "PUT"
            self.associations.add((g[1], g[2], g[3], g[4]))
            return httpx.Response(200, json={"status": "COMPLETE", "results": []})
        if p == "/crm/v3/pipelines/deals/default":
            return httpx.Response(200, json={"id": "default", "label": "Pipeline HubSpot", "stages": ETAPES_HS})
        return httpx.Response(599, json={"message": f"route inconnue du faux HubSpot : {m} {p}"})


@pytest.fixture()
def hs(client):
    faux = FauxHubspot()
    app.dependency_overrides[fournisseurs.get_crm_externe_provider] = faux.fournisseur
    yield faux
    app.dependency_overrides.pop(fournisseurs.get_crm_externe_provider, None)


def _ligne(session, objet_type: str, objet_id: int) -> SynchroHubspot | None:
    session.expire_all()
    return session.exec(select(SynchroHubspot).where(
        SynchroHubspot.objet_type == objet_type, SynchroHubspot.objet_id == objet_id)).first()


def _modifier(session, modele, ident: int, **champs):
    o = session.get(modele, ident)
    for k, v in champs.items():
        setattr(o, k, v)
    session.add(o)
    session.commit()
    return o


def _entreprise(session):
    org = creer_organisation(session, source="landing", ville="Strasbourg", site_web="https://www.exemple.test/accueil")
    c = creer_contact(session, type="entreprise", prenom="Prénom Test", nom="Nom Test", email="prenom@exemple.test",
                      organisation_id=org.id, poste="DRH", telephone="0300000000", ville="Strasbourg",
                      source_detail="landing-v1-galet")
    a = creer_affaire(session, "entreprises", "prospect", contact_id=c.id, organisation_id=org.id)
    return org, c, a


# --------------------------------------------------------------------------- marquage

def test_creation_et_modification_marquent_dans_la_meme_transaction(session, horloge):
    c = Contact(type="donateur", prenom="Prénom Test", source="manuel", cree_at=horloge(), maj_at=horloge())
    session.add(c)
    session.flush()
    session.rollback()
    assert session.exec(select(SynchroHubspot)).all() == []

    c = creer_contact(session, email="prenom@exemple.test")
    ligne = _ligne(session, "contact", c.id)
    assert (ligne.etat, ligne.essais, ligne.hubspot_id) == ("a_synchroniser", 0, None)
    ligne.etat, ligne.hubspot_id = "ok", "hs-1"
    session.add(ligne)
    session.commit()

    _modifier(session, Contact, c.id, ville="Strasbourg")
    ligne = _ligne(session, "contact", c.id)
    assert (ligne.etat, ligne.hubspot_id) == ("a_synchroniser", "hs-1")


# --------------------------------------------------------------------------- envoi

def test_upsert_contact_par_email_avec_proprietes_merci(session, horloge):
    faux = FauxHubspot()
    c = creer_contact(session, prenom="Prénom Test", nom="Nom Test", email="prenom@exemple.test",
                      telephone="0300000000", poste="Bénévole", ville="Strasbourg",
                      source_detail="instagram", consentement_at=horloge(), consentement_texte="Oui")
    synchro.envoyer(faux.fournisseur())

    [upsert] = faux.corps("batch/upsert")
    [entree] = upsert["inputs"]
    assert (entree["idProperty"], entree["id"]) == ("email", "prenom@exemple.test")
    assert entree["properties"] == {
        "firstname": "Prénom Test", "lastname": "Nom Test", "phone": "0300000000", "jobtitle": "Bénévole",
        "city": "Strasbourg", "merci_type": "donateur", "merci_source": "landing (instagram)",
        "merci_consentement": "2026-10-12", "merci_desinscrit": "",
    }
    ligne = _ligne(session, "contact", c.id)
    assert (ligne.etat, ligne.hubspot_id, ligne.essais, ligne.synchro_at) == ("ok", "101", 0, horloge())


def test_contact_sans_email_cree_puis_mis_a_jour_par_identifiant(session, horloge):
    faux = FauxHubspot()
    c = creer_contact(session, prenom="Prénom Test", email=None, linkedin_provider_id="factice-personne-1")
    synchro.envoyer(faux.fournisseur())
    assert faux.chemins("POST")[-1] == "POST /crm/v3/objects/contacts"
    hid = _ligne(session, "contact", c.id).hubspot_id

    _modifier(session, Contact, c.id, poste="DRH")
    synchro.envoyer(faux.fournisseur())
    assert faux.chemins()[-1] == f"PATCH /crm/v3/objects/contacts/{hid}"
    assert faux.objets["contacts"][hid]["jobtitle"] == "DRH" and len(faux.objets["contacts"]) == 1


def test_contact_connu_mis_a_jour_par_identifiant_meme_si_email_change(session, horloge):
    faux = FauxHubspot()
    c = creer_contact(session, email="prenom@exemple.test")
    synchro.envoyer(faux.fournisseur())
    hid = _ligne(session, "contact", c.id).hubspot_id
    _modifier(session, Contact, c.id, email="autre@exemple.test")
    synchro.envoyer(faux.fournisseur())
    [patch] = faux.corps(f"PATCH /crm/v3/objects/contacts/{hid}")
    assert patch["properties"]["email"] == "autre@exemple.test" and len(faux.objets["contacts"]) == 1


def test_company_contact_deal_et_associations_dans_l_ordre(session, horloge):
    faux = FauxHubspot()
    org, c, a = _entreprise(session)
    synchro.envoyer(faux.fournisseur())

    objets = [x for x in faux.chemins() if "/objects/" in x and "/associations/" not in x]
    assert objets == ["POST /crm/v3/objects/companies", "POST /crm/v3/objects/contacts/batch/upsert",
                      "POST /crm/v3/objects/deals"]
    [company] = faux.corps(r"POST /crm/v3/objects/companies$")
    assert company["properties"] == {"name": "Entreprise Test 1", "city": "Strasbourg", "domain": "exemple.test",
                                     "merci_type": "entreprise"}
    [deal] = faux.corps(r"POST /crm/v3/objects/deals$")
    assert deal["properties"] == {
        "dealname": "Entreprise Test 1 · Entreprises", "pipeline": "default", "dealstage": "etape-hs-1",
        "merci_pipeline": "Entreprises", "merci_etape": "Prospect",
    }
    co, ct, de = (_ligne(session, t, i).hubspot_id for t, i in
                  (("organisation", org.id), ("contact", c.id), ("affaire", a.id)))
    assert faux.associations == {("0-1", ct, "0-2", co), ("0-3", de, "0-1", ct), ("0-3", de, "0-2", co)}
    assert {_ligne(session, t, i).etat for t, i in (("organisation", org.id), ("contact", c.id),
                                                    ("affaire", a.id))} == {"ok"}


def test_montant_mensuel_envoye_comme_amount(session, horloge):
    faux = FauxHubspot()
    _, _, a = _entreprise(session)
    _modifier(session, Affaire, a.id, montant_mensuel=Decimal("49.00"))
    synchro.envoyer(faux.fournisseur())
    [deal] = faux.corps(r"POST /crm/v3/objects/deals$")
    assert deal["properties"]["amount"] == "49.00"


def test_proprietes_custom_creees_une_seule_fois(session, horloge):
    faux = FauxHubspot()
    c = creer_contact(session, email="prenom@exemple.test")
    synchro.envoyer(faux.fournisseur())
    creees = faux.corps(r"POST /crm/v3/properties/\w+$")
    assert {(p["name"], p["groupName"]) for p in creees} == {
        ("merci_type", "merci"), ("merci_source", "merci"), ("merci_consentement", "merci"),
        ("merci_desinscrit", "merci"), ("merci_pipeline", "merci"), ("merci_etape", "merci")}
    assert faux.groupes == {"contacts": {"merci"}, "companies": {"merci"}, "deals": {"merci"}}
    assert {p["label"] for p in faux.corps(r"POST /crm/v3/properties/\w+/groups$")} == {"MERCI"}

    avant = len(faux.requetes)
    _modifier(session, Contact, c.id, ville="Strasbourg")
    synchro.envoyer(faux.fournisseur())
    assert faux.chemins()[avant:] and [x for x in faux.chemins()[avant:] if "/properties/" in x] == []


def test_desinscription_renseigne_merci_desinscrit(client, session, horloge, hs):
    c = creer_contact(session, email="prenom@exemple.test")
    assert client.get(f"/public/desinscription/{securite.jeton_desinscription(c.id)}").status_code == 200
    assert hs.contact("prenom@exemple.test")["merci_desinscrit"] == "2026-10-12"


# --------------------------------------------------------------------------- déclenchement par l'API

def test_changement_d_etape_met_a_jour_le_deal_sans_en_creer_un_second(client_connecte, session, horloge, hs):
    _, _, a = _entreprise(session)
    synchro.envoyer(hs.fournisseur())
    hid = _ligne(session, "affaire", a.id).hubspot_id

    r = client_connecte.patch(f"/affaires/{a.id}", json={"etape": "contacte"})
    assert r.status_code == 200
    assert len(hs.objets["deals"]) == 1
    assert hs.objets["deals"][hid]["merci_etape"] == "Contacté"
    assert "dealstage" not in hs.corps(f"PATCH /crm/v3/objects/deals/{hid}")[-1]["properties"]
    assert _ligne(session, "affaire", a.id).etat == "ok"


def test_correspondance_d_etapes_reglee_par_l_admin(client_connecte, session, horloge, hs):
    r = client_connecte.patch("/reglages", json={"hubspot_etapes": {"entreprises": {"contacte": "etape-hs-2"}}})
    assert r.status_code == 200
    assert r.json()["hubspot_etapes"] == {"donateurs": {}, "entreprises": {"contacte": "etape-hs-2"},
                                          "associations": {}}
    assert client_connecte.get("/reglages").json()["hubspot_etapes"]["entreprises"] == {"contacte": "etape-hs-2"}
    assert client_connecte.patch("/reglages", json={"hubspot_etapes": {"entreprises": {"inconnue": "x"}}}
                                 ).status_code == 422

    _, _, a = _entreprise(session)
    client_connecte.patch(f"/affaires/{a.id}", json={"etape": "contacte"})
    [deal] = hs.objets["deals"].values()
    assert (deal["dealstage"], deal["merci_etape"]) == ("etape-hs-2", "Contacté")

    assert client_connecte.get("/hubspot/etapes").json() == {"etapes": [
        {"id": "etape-hs-1", "label": "Étape HubSpot 1"}, {"id": "etape-hs-2", "label": "Étape HubSpot 2"}]}


def test_routes_hubspot_reservees_a_l_admin(client, session, horloge, hs):
    connecter(client, creer_membre(session, "prenom@exemple.test"))
    r = client.patch("/reglages", json={"hubspot_etapes": {"entreprises": {"contacte": "etape-hs-2"}}})
    assert r.status_code == 403
    assert client.get("/hubspot/etat").status_code == 403
    assert client.post("/hubspot/tout-synchroniser").status_code == 403
    assert client.get("/hubspot/etapes").status_code == 403


def test_capture_landing_declenche_la_synchro(client, session, horloge, hs, sans_envoi_immediat):
    assert inscrire_landing(client, "entreprise").status_code == 201
    c = session.exec(select(Contact)).one()
    assert hs.contact("prenom@exemple.test")["merci_type"] == "entreprise"
    assert len(hs.objets["companies"]) == 1 and len(hs.objets["deals"]) == 1
    assert _ligne(session, "contact", c.id).etat == "ok"
    assert _ligne(session, "organisation", c.organisation_id).etat == "ok"


def test_contact_cree_a_la_main_part_vers_hubspot(client_connecte, session, horloge, hs):
    r = client_connecte.post("/contacts", json={"type": "donateur", "prenom": "Prénom Test",
                                                "email": "prenom@exemple.test"})
    assert r.status_code == 201
    assert hs.contact("prenom@exemple.test")["merci_source"] == "manuel"
    fiche = client_connecte.get(f"/contacts/{r.json()['id']}").json()
    assert fiche["hubspot"] == {"etat": "ok", "message": None, "synchro_at": "2026-10-12T08:00:00Z"}


# --------------------------------------------------------------------------- reprise, plafond, secret

def test_tick_reprend_apres_429_puis_500(client, session, horloge, hs):
    c = creer_contact(session, email="prenom@exemple.test")
    hs.pannes = [(429, {"status": "error", "message": "You have reached your ten_secondly_rolling limit.",
                        "errorType": "RATE_LIMIT", "policyName": "TEN_SECONDLY_ROLLING"})]
    tick(client)
    ligne = _ligne(session, "contact", c.id)
    assert (ligne.etat, ligne.essais) == ("erreur", 1)
    assert "429" in ligne.derniere_erreur and ligne.prochain_essai_at > horloge()

    n = len(hs.requetes)
    tick(client)                       # trop tôt : pas de nouvel essai
    assert len(hs.requetes) == n

    horloge.avancer(minutes=2)
    hs.pannes = [(500, {"message": "erreur interne"})]
    tick(client)
    ligne = _ligne(session, "contact", c.id)
    assert (ligne.etat, ligne.essais) == ("erreur", 2) and "500" in ligne.derniere_erreur

    horloge.avancer(hours=1)
    tick(client)
    ligne = _ligne(session, "contact", c.id)
    assert (ligne.etat, ligne.essais, ligne.derniere_erreur) == ("ok", 0, None)
    assert len(hs.objets["contacts"]) == 1


def test_plafond_d_essais(client, session, horloge, hs):
    c = creer_contact(session, email="prenom@exemple.test")
    hs.panne_permanente = (503, {"message": "indisponible"})
    for _ in range(synchro.ESSAIS_MAX + 2):
        tick(client)
        horloge.avancer(hours=6)
    ligne = _ligne(session, "contact", c.id)
    assert (ligne.etat, ligne.essais, ligne.prochain_essai_at) == ("erreur", synchro.ESSAIS_MAX, None)
    n = len(hs.requetes)
    tick(client)
    assert len(hs.requetes) == n

    _modifier(session, Contact, c.id, ville="Strasbourg")   # une nouvelle modification relance les essais
    ligne = _ligne(session, "contact", c.id)
    assert (ligne.etat, ligne.essais) == ("a_synchroniser", 0)


def test_jeton_jamais_dans_erreurs_journaux_ni_reponses(client_connecte, session, horloge, hs, caplog):
    caplog.set_level(logging.DEBUG)
    creer_contact(session, email="prenom@exemple.test")
    hs.panne_permanente = (401, {"message": f"Authentication credentials not found: {JETON}"})
    tick(client_connecte)
    ligne = session.exec(select(SynchroHubspot)).one()
    assert "401" in ligne.derniere_erreur and JETON not in ligne.derniere_erreur
    etat = client_connecte.get("/hubspot/etat")
    assert JETON not in etat.text and JETON not in caplog.text
    assert JETON not in repr(hs.fournisseur()) and JETON not in str(vars(hs.fournisseur()))
    assert etat.json()["dernieres_erreurs"][0]["message"].startswith("HubSpot refuse le jeton")


def test_message_d_erreur_hubspot_expurge_du_jeton(session, horloge):
    faux = FauxHubspot()
    creer_contact(session, email="prenom@exemple.test")
    faux.panne_permanente = (400, {"message": f"Valeur refusée, jeton {JETON}"})
    synchro.envoyer(faux.fournisseur())
    ligne = session.exec(select(SynchroHubspot)).one()
    assert ligne.derniere_erreur.startswith("HubSpot refuse les données (HTTP 400)") and JETON not in ligne.derniere_erreur


def test_fournisseur_factice_sans_cle(session, horloge, monkeypatch, caplog):
    monkeypatch.setattr(settings, "hubspot_token", "")
    crm = fournisseurs.get_crm_externe_provider()
    assert isinstance(crm, FauxCrmProvider) and crm.connecte is False
    monkeypatch.setattr(settings, "hubspot_token", JETON)
    assert isinstance(fournisseurs.get_crm_externe_provider(), HubspotCrmProvider)

    caplog.set_level(logging.INFO, logger="merci.hubspot")
    c = creer_contact(session, email="prenom@exemple.test")
    synchro.envoyer(crm)           # le réseau est bloqué par conftest : rien n'est appelé
    assert "prenom@exemple.test" in caplog.text and "factice" in caplog.text
    ligne = _ligne(session, "contact", c.id)
    assert (ligne.etat, ligne.hubspot_id) == ("a_synchroniser", None)


# --------------------------------------------------------------------------- routes et fiche

def test_etat_et_tout_synchroniser(client_connecte, session, horloge, hs):
    vide = client_connecte.get("/hubspot/etat").json()
    assert vide == {"etat": "connecte", "compteurs": {"synchronises": 0, "en_attente": 0, "en_erreur": 0},
                    "dernieres_erreurs": [], "derniere_synchro_at": None}

    _entreprise(session)
    for ligne in session.exec(select(SynchroHubspot)).all():   # objets antérieurs à la synchro
        session.delete(ligne)
    session.commit()
    r = client_connecte.post("/hubspot/tout-synchroniser")
    assert r.status_code == 202 and r.json() == {"marques": 3}
    etat = client_connecte.get("/hubspot/etat").json()
    assert etat["compteurs"] == {"synchronises": 3, "en_attente": 0, "en_erreur": 0}
    assert etat["derniere_synchro_at"] == "2026-10-12T08:00:00Z"


def test_etat_non_connecte_sans_cle(client_connecte, session, horloge):
    creer_contact(session, email="prenom@exemple.test")
    etat = client_connecte.get("/hubspot/etat").json()
    assert etat["etat"] == "non_connecte" and etat["compteurs"]["en_attente"] == 1
    assert client_connecte.get("/hubspot/etapes").status_code == 409


def test_fiche_contact_mentionne_l_erreur_hubspot(client_connecte, session, horloge, hs):
    c = creer_contact(session, email="prenom@exemple.test")
    hs.panne_permanente = (400, {"message": "Property values were not valid"})
    tick(client_connecte)
    fiche = client_connecte.get(f"/contacts/{c.id}").json()
    assert fiche["hubspot"]["etat"] == "erreur"
    assert fiche["hubspot"]["message"].startswith("HubSpot refuse les données (HTTP 400)")
    etat = client_connecte.get("/hubspot/etat").json()
    assert etat["etat"] == "erreurs" and etat["dernieres_erreurs"][0]["nom"] == "Prénom Test"
