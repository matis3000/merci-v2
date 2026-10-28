from __future__ import annotations

import json
import re

from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app import auth, db as db_mod, securite
from app.config import settings
from app.main import app, create_app
from app.modeles import JetonConnexion, Membre
from conftest import connecter, creer_membre

PROXY = {"X-Forwarded-For": "203.0.113.7"}

# Routes sans session (section 9.5). Tout le reste exige le cookie.
OUVERTES = ("/auth/lien", "/auth/verifier", "/auth/deconnexion", "/health", "/ready")
PREFIXES_OUVERTS = ("/public/", "/cron/", "/webhooks/")


def _demander(client: TestClient, email: str, **kw):
    return client.post("/auth/lien", json={"email": email}, **kw)


def _jeton(client: TestClient, email: str) -> str:
    lien = _demander(client, email).json()["dev_lien"]
    return lien.split("jeton=", 1)[1]


def test_demande_lien_reponse_identique_membre_inconnu(client, membre, fournisseurs_factices):
    connu = _demander(client, "prenom@exemple.test", headers=PROXY)
    inconnu = _demander(client, "inconnu@exemple.test", headers=PROXY)
    assert connu.status_code == inconnu.status_code == 200
    assert connu.json() == inconnu.json() == {"ok": True}
    envois = fournisseurs_factices.emails()
    assert len(envois) == 1  # seul le membre reçoit un lien
    assert json.loads(envois[0].read_text())["a"] == "prenom@exemple.test"


def test_demande_lien_membre_inactif_rien_envoye(client, session, fournisseurs_factices):
    creer_membre(session, "prenom@exemple.test", actif=False)
    r = _demander(client, "prenom@exemple.test")
    assert r.json() == {"ok": True}
    assert fournisseurs_factices.emails() == []


def test_demande_lien_email_invalide_422(client):
    assert _demander(client, "pas-une-adresse").status_code == 422


def test_demande_lien_stocke_un_hash_jamais_le_jeton(client, membre, session, fournisseurs_factices):
    jeton = _jeton(client, "Prenom@Exemple.TEST")
    ligne = session.exec(select(JetonConnexion)).one()
    assert ligne.email == "prenom@exemple.test"
    assert ligne.jeton_hash == auth.hash_magic_token(jeton)
    assert jeton not in ligne.jeton_hash
    contenu = fournisseurs_factices.emails()[0].read_text()
    assert jeton in contenu  # le jeton ne vit que dans l'e-mail


def test_dev_lien_seulement_en_local_et_en_developpement(client, membre, monkeypatch):
    r = _demander(client, "prenom@exemple.test")
    assert re.fullmatch(r"http://127\.0\.0\.1:3000/connexion/verifier\?jeton=[\w-]{40,}", r.json()["dev_lien"])
    assert "dev_lien" not in _demander(client, "prenom@exemple.test", headers=PROXY).json()
    monkeypatch.setattr(settings, "mode", "production")
    assert "dev_lien" not in _demander(client, "prenom@exemple.test").json()


def test_demande_lien_limite_5_par_minute_429(client, horloge):
    for _ in range(5):
        assert _demander(client, "inconnu@exemple.test").status_code == 200
    assert _demander(client, "inconnu@exemple.test").status_code == 429
    horloge.avancer(seconds=61)
    assert _demander(client, "inconnu@exemple.test").status_code == 200


def test_verifier_pose_cookie_httponly(client, membre, session):
    jeton = _jeton(client, "prenom@exemple.test")
    client.cookies.clear()
    r = client.post("/auth/verifier", json={"jeton": jeton})
    assert r.status_code == 200
    assert r.json() == {"membre": {"id": membre.id, "email": "prenom@exemple.test",
                                   "prenom": "Prénom Test", "role": "equipe", "actif": True}}
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("merci_session=")
    for attendu in ("HttpOnly", "Path=/", "SameSite=lax", f"Max-Age={7 * 86400}"):
        assert attendu.lower() in cookie.lower()
    assert "secure" not in cookie.lower()  # Secure seulement en production
    assert client.get("/auth/moi").json()["email"] == "prenom@exemple.test"
    session.refresh(membre)
    assert membre.derniere_connexion_at is not None


def test_cookie_secure_en_production(client, membre, monkeypatch):
    jeton = _jeton(client, "prenom@exemple.test")
    monkeypatch.setattr(settings, "mode", "production")
    r = client.post("/auth/verifier", json={"jeton": jeton})
    assert "secure" in r.headers["set-cookie"].lower()


def test_lien_expire_apres_15_minutes_refuse(client, membre, horloge):
    jeton = _jeton(client, "prenom@exemple.test")
    horloge.avancer(minutes=15, seconds=1)
    r = client.post("/auth/verifier", json={"jeton": jeton})
    assert r.status_code == 401
    assert r.json() == {"detail": "Lien invalide ou expiré, demandez-en un nouveau"}


def test_lien_valide_avant_15_minutes(client, membre, horloge):
    jeton = _jeton(client, "prenom@exemple.test")
    horloge.avancer(minutes=14, seconds=59)
    assert client.post("/auth/verifier", json={"jeton": jeton}).status_code == 200


def test_lien_usage_unique(client, membre):
    jeton = _jeton(client, "prenom@exemple.test")
    assert client.post("/auth/verifier", json={"jeton": jeton}).status_code == 200
    assert client.post("/auth/verifier", json={"jeton": jeton}).status_code == 401


def test_jeton_inconnu_401(client):
    assert client.post("/auth/verifier", json={"jeton": "x" * 43}).status_code == 401


def test_membre_inactif_refuse(client, membre, session):
    jeton = _jeton(client, "prenom@exemple.test")
    connecter(client, membre)
    membre.actif = False
    session.add(membre)
    session.commit()
    r = client.post("/auth/verifier", json={"jeton": jeton})
    assert r.status_code == 403
    assert r.json() == {"detail": "Compte désactivé"}
    assert client.get("/auth/moi").status_code == 401  # session existante refusée aussi


def test_moi_sans_cookie_401(client):
    assert client.get("/auth/moi").status_code == 401
    client.cookies.set(auth.COOKIE_SESSION, "jeton.falsifie.x")
    assert client.get("/auth/moi").status_code == 401


def test_session_expiree_401(client, membre, horloge):
    connecter(client, membre)
    assert client.get("/auth/moi").status_code == 200
    horloge.avancer(days=7, seconds=1)
    assert client.get("/auth/moi").status_code == 401


def test_deconnexion_efface_cookie(client, membre):
    jeton = _jeton(client, "prenom@exemple.test")
    client.post("/auth/verifier", json={"jeton": jeton})
    assert client.get("/auth/moi").status_code == 200
    r = client.post("/auth/deconnexion")
    assert r.status_code == 204
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("merci_session=") and "max-age=0" in cookie.lower()
    assert "httponly" in cookie.lower()
    assert client.get("/auth/moi").status_code == 401


def _apiroutes(routes):
    for route in routes:
        if isinstance(route, APIRoute):
            yield route
        elif hasattr(route, "original_router"):  # routeur inclus (FastAPI récent)
            yield from _apiroutes(route.original_router.routes)


def _routes_api():
    for route in _apiroutes(app.routes):
        for methode in route.methods:
            yield methode, route


def test_enumeration_des_routes_complete():
    vues = {(m.lower(), r.path) for m, r in _routes_api()}
    publiees = {(m, chemin) for chemin, ops in app.openapi()["paths"].items() for m in ops}
    assert publiees <= vues
    assert ("get", "/auth/moi") in vues


def _chemin(route: APIRoute) -> str:
    return re.sub(r"\{[^}]+\}", "1", route.path)


def _depend_de(route: APIRoute, fn) -> bool:
    pile = [route.dependant]
    while pile:
        d = pile.pop()
        if d.call is fn:
            return True
        pile.extend(d.dependencies)
    return False


def test_toutes_les_routes_crm_exigent_une_session(client):
    verifiees = 0
    for methode, route in _routes_api():
        if route.path in OUVERTES or route.path.startswith(PREFIXES_OUVERTS):
            continue
        r = client.request(methode, _chemin(route))
        assert r.status_code == 401, f"{methode} {route.path} sans session : {r.status_code}"
        verifiees += 1
    assert verifiees >= 1  # au moins /auth/moi


def test_routes_admin_refusent_le_role_equipe(client, membre, admin, engine):
    connecter(client, membre)
    for methode, route in _routes_api():
        if _depend_de(route, auth.admin_requis):
            r = client.request(methode, _chemin(route))
            assert r.status_code == 403, f"{methode} {route.path} : {r.status_code}"

    # La dépendance elle-même, sur une route d'essai.
    essai = FastAPI()

    @essai.get("/reserve-admin")
    def reserve(m: Membre = Depends(auth.admin_requis)):
        return {"id": m.id}

    def _get_session():
        with Session(engine) as s:
            yield s

    essai.dependency_overrides[db_mod.get_session] = _get_session
    c = TestClient(essai)
    assert connecter(c, membre).get("/reserve-admin").status_code == 403
    assert connecter(c, admin).get("/reserve-admin").json() == {"id": admin.id}


def test_admin_cree_au_demarrage_depuis_admin_email(engine, session, fournisseurs_factices):
    for _ in range(2):  # deux démarrages : création idempotente
        with TestClient(create_app()):
            pass
    admins = session.exec(select(Membre)).all()
    assert [(m.email, m.prenom, m.role, m.actif) for m in admins] == [
        ("admin@exemple.test", "Admin Test", "admin", True)]


def test_secrets_compares_a_temps_constant():
    assert securite.secrets_egaux("abc", "abc")
    assert not securite.secrets_egaux("abc", "abd")
    assert not securite.secrets_egaux("", "")  # secret non configuré : toujours refusé


def test_jeton_desinscription_signe():
    j = securite.jeton_desinscription(42)
    assert securite.lire_jeton_desinscription(j) == 42
    assert securite.lire_jeton_desinscription(j[:-1] + ("A" if j[-1] != "A" else "B")) is None
    autre = securite.jeton_desinscription(43)
    assert securite.lire_jeton_desinscription(autre.split(".")[0] + "." + j.split(".")[1]) is None
    assert securite.lire_jeton_desinscription("n'importe quoi") is None
