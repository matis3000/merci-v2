"""Fournisseurs e-mail : boîte locale, Resend (transport simulé), signature Svix, choix (section 6)."""
from __future__ import annotations

import base64
import calendar
import hashlib
import hmac
import json

import httpx
import pytest

from app import fournisseurs
from app.config import settings
from app.fournisseurs.base import ErreurFournisseur, MessageEmail, NonConfigure, SignatureInvalide
from app.fournisseurs.email_console import ConsoleEmailProvider
from app.fournisseurs.email_resend import ResendEmailProvider

CLE = "re_cle_secrete_de_test_123"
SECRET = "whsec_" + base64.b64encode(b"secret-webhook-de-test-0123456789").decode()


def _message() -> MessageEmail:
    return MessageEmail(
        a="prenom@exemple.test", sujet="Sujet de test", html="<p>Bonjour</p>", texte="Bonjour",
        expediteur="MERCI <bonjour@exemple.test>", repondre_a="equipe@exemple.test",
        entetes={"List-Unsubscribe": "<http://127.0.0.1:8010/public/desinscription/x>",
                 "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
        cle_idempotence="envoi-1-1-1", etiquettes={"inscription_id": "1", "pas": "1"},
    )


def test_console_email_ecrit_dans_outbox(tmp_path, horloge):
    ident = ConsoleEmailProvider(dossier=tmp_path).envoyer(_message())
    [fichier] = list(tmp_path.glob("*.json"))
    assert fichier.name.startswith("20261012-080000_envoi-1-1-1")
    contenu = json.loads(fichier.read_text())
    assert ident.startswith("console-") and contenu["id"] == ident
    assert (contenu["a"], contenu["sujet"], contenu["texte"]) == ("prenom@exemple.test", "Sujet de test", "Bonjour")
    assert contenu["entetes"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert fichier.with_suffix(".html").read_text() == "<p>Bonjour</p>"


def test_resend_envoi_entetes_et_idempotency_key():
    recues: list[httpx.Request] = []

    def repondre(request):
        recues.append(request)
        return httpx.Response(200, json={"id": "re-identifiant-1"})

    p = ResendEmailProvider(CLE, SECRET, transport=httpx.MockTransport(repondre))
    assert p.envoyer(_message()) == "re-identifiant-1"
    [req] = recues
    assert (req.method, str(req.url)) == ("POST", "https://api.resend.com/emails")
    assert req.headers["Authorization"] == f"Bearer {CLE}"
    assert req.headers["Idempotency-Key"] == "envoi-1-1-1"
    corps = json.loads(req.content)
    assert corps["from"] == "MERCI <bonjour@exemple.test>" and corps["to"] == ["prenom@exemple.test"]
    assert (corps["subject"], corps["html"], corps["text"]) == ("Sujet de test", "<p>Bonjour</p>", "Bonjour")
    assert corps["reply_to"] == "equipe@exemple.test"
    assert corps["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert {"name": "inscription_id", "value": "1"} in corps["tags"]


@pytest.mark.parametrize("reponse", [
    httpx.Response(500, text="erreur interne"),
    httpx.Response(429, text="trop de requêtes"),
    httpx.Response(422, json={"message": f"clé {CLE} refusée"}),
    httpx.Response(200, text="pas du json"),
    None,
])
def test_resend_erreur_sans_cle_dans_le_message(reponse):
    def repondre(request):
        if reponse is None:
            raise httpx.ConnectError("connexion impossible", request=request)
        return reponse

    p = ResendEmailProvider(CLE, SECRET, transport=httpx.MockTransport(repondre))
    with pytest.raises(ErreurFournisseur) as e:
        p.envoyer(_message())
    assert str(e.value).startswith("Resend : ")
    assert CLE not in str(e.value)
    if reponse is not None and reponse.status_code != 200:
        assert str(e.value) == f"Resend : HTTP {reponse.status_code}"


def test_svix_signature_valide_acceptee(horloge):
    corps = json.dumps({"type": "email.opened", "created_at": "2026-10-12T08:00:00Z",
                        "data": {"email_id": "re-identifiant-1"}}).encode()
    ts = str(calendar.timegm(horloge.t.timetuple()))
    mac = hmac.new(base64.b64decode(SECRET[6:]), f"msg_1.{ts}.".encode() + corps, hashlib.sha256).digest()
    bonne = base64.b64encode(mac).decode()
    p = ResendEmailProvider(CLE, SECRET)
    entetes = {"svix-id": "msg_1", "svix-timestamp": ts, "svix-signature": f"v1,ZmF1c3Nl v1,{bonne}"}
    [ev] = p.analyser_webhook(entetes, corps)
    assert (ev.cle, ev.type, ev.fournisseur_id, ev.recu_at) == ("msg_1", "ouvert", "re-identifiant-1", horloge.t)
    with pytest.raises(SignatureInvalide):
        p.analyser_webhook(entetes, corps + b" ")
    with pytest.raises(SignatureInvalide):
        ResendEmailProvider(CLE, "").analyser_webhook(entetes, corps)


def test_production_refuse_les_fournisseurs_factices(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "resend_api_key", "")
    assert isinstance(fournisseurs.get_email_provider(), ConsoleEmailProvider)
    monkeypatch.setattr(settings, "mode", "production")
    with pytest.raises(NonConfigure):
        fournisseurs.get_email_provider()
    with pytest.raises(SignatureInvalide):
        ConsoleEmailProvider(dossier=tmp_path).analyser_webhook({}, b'{"type":"email.opened","data":{"email_id":"x"}}')
    monkeypatch.setattr(settings, "resend_api_key", CLE)
    assert isinstance(fournisseurs.get_email_provider(), ResendEmailProvider)


# --------------------------------------------------------------------------- LinkedIn (lot L5)

import datetime as dt  # noqa: E402

from app.fournisseurs.base import CompteLinkedInDeconnecte  # noqa: E402
from app.fournisseurs.linkedin_connectsafely import ConnectSafelyLinkedInProvider  # noqa: E402
from app.fournisseurs.linkedin_factice import FauxLinkedInProvider  # noqa: E402


def test_faux_linkedin_ne_trouve_personne_par_defaut(tmp_path, horloge):
    f = FauxLinkedInProvider(dossier=tmp_path)
    assert f.nom == "factice" and f.etat_compte() == "ok"
    assert f.chercher("Entreprise Test 1", ["DRH"], 2) == []
    assert f.profil("factice-personne-1").posts_recents == []
    ident = f.inviter("factice-personne-1", "Bonjour")
    assert ident.startswith("factice-")
    [ligne] = (tmp_path / "linkedin.jsonl").read_text().splitlines()
    assert json.loads(ligne) == {"id": ident, "action": "inviter", "provider_id": "factice-personne-1",
                                 "texte": "Bonjour", "at": "2026-10-12T08:00:00Z"}
    [ev] = f.analyser_webhook({}, json.dumps({"evenements": [
        {"cle": "e-1", "type": "message_recu", "provider_id": "factice-personne-1", "texte": "Oui"}]}).encode())
    assert (ev.cle, ev.type, ev.provider_id, ev.texte, ev.recu_at) == (
        "e-1", "message_recu", "factice-personne-1", "Oui", horloge.t)


def test_production_refuse_le_linkedin_factice(monkeypatch):
    assert isinstance(fournisseurs.get_linkedin_provider(), FauxLinkedInProvider)
    monkeypatch.setattr(settings, "mode", "production")
    with pytest.raises(NonConfigure):
        fournisseurs.get_linkedin_provider()
    with pytest.raises(SignatureInvalide):
        FauxLinkedInProvider().analyser_webhook({}, b'{"evenements": []}')
    monkeypatch.setattr(settings, "linkedin_fournisseur", "connectsafely")
    with pytest.raises(NonConfigure):
        fournisseurs.get_linkedin_provider()
    monkeypatch.setattr(settings, "connectsafely_api_key", "cle")
    monkeypatch.setattr(settings, "connectsafely_account_id", "compte-test")
    assert isinstance(fournisseurs.get_linkedin_provider(), ConnectSafelyLinkedInProvider)


# --------------------------------------------------------------------------- ConnectSafely

CLE_CS = "cle-connectsafely-secrete-123"


def _cs(repondre, secret: str = "secret-cs") -> ConnectSafelyLinkedInProvider:
    return ConnectSafelyLinkedInProvider(CLE_CS, "compte-test", secret_webhook=secret,
                                         transport=httpx.MockTransport(repondre))


def test_connectsafely_inviter_et_ecrire():
    recues = []

    def repondre(request):
        recues.append(request)
        return httpx.Response(200, json={"success": True, "message": "ok",
                                         "profileUrn": "urn:li:fsd_profile:factice-1",
                                         "recipientProfileUrn": "urn:li:fsd_profile:factice-1"})

    p = _cs(repondre)
    assert p.inviter("urn:li:fsd_profile:factice-1", "Bonjour")
    assert p.ecrire("urn:li:fsd_profile:factice-1", "Merci")
    inv, msg = recues
    assert str(inv.url) == "https://api.connectsafely.ai/linkedin/connect"
    assert inv.headers["Authorization"] == f"Bearer {CLE_CS}"
    assert json.loads(inv.content) == {"accountId": "compte-test", "profileUrn": "urn:li:fsd_profile:factice-1",
                                       "customMessage": "Bonjour"}
    assert str(msg.url) == "https://api.connectsafely.ai/linkedin/message"
    assert json.loads(msg.content) == {"accountId": "compte-test", "recipientProfileUrn": "urn:li:fsd_profile:factice-1",
                                       "message": "Merci", "messageType": "normal"}
    with pytest.raises(CompteLinkedInDeconnecte):
        _cs(lambda r: httpx.Response(401, json={"error": "Unauthorized"})).inviter("urn:li:fsd_profile:x", "B")
    with pytest.raises(ErreurFournisseur) as e:
        _cs(lambda r: httpx.Response(429)).inviter("urn:li:fsd_profile:x", "B")
    assert str(e.value) == "ConnectSafely : HTTP 429"


def test_connectsafely_chercher_profil_etat(horloge):
    def repondre(request):
        if request.url.path == "/linkedin/search/people":
            assert json.loads(request.content) == {"accountId": "compte-test", "keywords": "DRH OR RH", "count": 10,
                                                   "filters": {"company": "Entreprise Test 1"}}
            return httpx.Response(200, json={"success": True, "people": [
                {"profileId": "prenom1-test", "profileUrn": "urn:li:fsd_profile:factice-1", "firstName": "Prénom1",
                 "lastName": "Test", "headline": "DRH", "profileUrl": "https://www.linkedin.com/in/prenom1-test/"},
                {"profileId": "prenom2-test", "profileUrn": "urn:li:fsd_profile:factice-2", "firstName": "Prénom2",
                 "lastName": "Test", "headline": "Comptable"}], "hasMore": False})
        if request.url.path == "/linkedin/posts/latest":
            assert json.loads(request.content)["profileUrn"] == "urn:li:fsd_profile:factice-1"
            return httpx.Response(200, json={"success": True, "posts": [
                {"content": "Notre démarche RSE", "timestamp": "1w"},
                {"content": "Ancien", "timestamp": "2mo"}]})
        assert request.url.path == "/linkedin/account/compte-test/status"
        return httpx.Response(200, json={"id": "compte-test", "status": "AVAILABLE", "enabled": True,
                                         "hasTokens": True})

    p = _cs(repondre)
    [x] = p.chercher("Entreprise Test 1", ["DRH", "RH"], 2)
    assert (x.provider_id, x.prenom, x.poste) == ("urn:li:fsd_profile:factice-1", "Prénom1", "DRH")
    assert p.profil("urn:li:fsd_profile:factice-1").posts_recents == [
        (horloge.t - dt.timedelta(days=7), "Notre démarche RSE")]
    assert p.etat_compte() == "ok"
    erreur = _cs(lambda r: httpx.Response(200, json={"status": "ERROR", "enabled": True, "hasTokens": True}))
    assert erreur.etat_compte() == "a_reconnecter"


def test_connectsafely_webhook_signe(horloge):
    import calendar
    p = _cs(lambda r: httpx.Response(500))
    corps = json.dumps({"event": "message.received", "object": "event", "data": {
        "id": "urn:li:messagingMessage:test-1", "message_urn": "urn:li:messagingMessage:test-1",
        "account_id": "compte-test", "provider": "LINKEDIN",
        "sender": {"id": "urn:li:fsd_profile:factice-1", "name": "Prénom1 Test"},
        "body": "Avec plaisir", "timestamp": "2026-10-12T08:00:00.000Z",
        "conversation_id": "urn:li:messagingThread:test-1", "attachments": []}}).encode()
    ts = str(calendar.timegm(horloge.t.timetuple()))
    sig = "sha256=" + hmac.new(b"secret-cs", corps, hashlib.sha256).hexdigest()
    [ev] = p.analyser_webhook({"X-Webhook-Signature": sig, "X-Webhook-Timestamp": ts}, corps)
    assert (ev.cle, ev.type, ev.provider_id, ev.texte) == (
        "urn:li:messagingMessage:test-1", "message_recu", "urn:li:fsd_profile:factice-1", "Avec plaisir")
    with pytest.raises(SignatureInvalide):
        p.analyser_webhook({"X-Webhook-Signature": "sha256=00", "X-Webhook-Timestamp": ts}, corps)
    with pytest.raises(SignatureInvalide):
        p.analyser_webhook({"X-Webhook-Signature": sig, "X-Webhook-Timestamp": str(int(ts) - 301)}, corps)


def test_connectsafely_inviter_note_300_caracteres():
    recues = []
    p = _cs(lambda r: recues.append(r) or httpx.Response(200, json={"success": True}))
    note = "Bonjour Prénom Test, " + "x" * 279
    assert len(note) == 300
    assert p.inviter("urn:li:fsd_profile:factice-1", note).startswith("connectsafely-")
    [req] = recues
    assert json.loads(req.content)["customMessage"] == note
    with pytest.raises(ErreurFournisseur) as e:
        p.inviter("urn:li:fsd_profile:factice-1", note + "x")
    assert "300" in str(e.value) and len(recues) == 1  # refus avant tout appel


@pytest.mark.parametrize("code", [401, 403])
def test_connectsafely_401_403_devient_compte_deconnecte(code):
    p = _cs(lambda r: httpx.Response(code, json={"error": "Unauthorized", "detail": CLE_CS}))
    for appel in (lambda: p.inviter("urn:li:fsd_profile:x", "Bonjour"), lambda: p.ecrire("urn:li:fsd_profile:x", "Bonjour")):
        with pytest.raises(CompteLinkedInDeconnecte) as e:
            appel()
        assert str(e.value) == f"ConnectSafely : HTTP {code}" and CLE_CS not in str(e.value)


def test_connectsafely_erreurs_transitoires_sans_cle():
    for reponse in (httpx.Response(500), httpx.Response(429), httpx.Response(200, text="pas du json"),
                    httpx.Response(200, json={"success": False, "error": CLE_CS})):
        p = _cs(lambda r, rep=reponse: rep)
        with pytest.raises(ErreurFournisseur) as e:
            p.inviter("urn:li:fsd_profile:x", "Bonjour")
        assert not isinstance(e.value, CompteLinkedInDeconnecte) and CLE_CS not in str(e.value)

    def coupure(request):
        raise httpx.ConnectError("coupure", request=request)
    with pytest.raises(ErreurFournisseur) as e:
        _cs(coupure).ecrire("urn:li:fsd_profile:x", "Bonjour")
    assert str(e.value) == "ConnectSafely : erreur réseau (ConnectError)"


def test_connectsafely_chercher_limite_et_filtre_intitule():
    def personne(n, poste):
        return {"profileUrn": f"urn:li:fsd_profile:factice-{n}", "firstName": f"Prénom{n}", "lastName": "Test",
                "headline": poste, "profileUrl": f"https://www.linkedin.com/in/prenom{n}-test/"}
    p = _cs(lambda r: httpx.Response(200, json={"success": True, "people": [
        personne(1, "DRH chez Entreprise Test 1"), personne(2, "Directeur commercial"),
        {"firstName": "Sans", "headline": "DRH"},  # sans profileUrn : ignoré
        personne(3, "Responsable RSE"), personne(4, "Chargée RH")]}))
    personnes = p.chercher("Entreprise Test 1", ["DRH", "RH", "RSE"], limite=2)
    assert [(x.provider_id, x.prenom, x.nom, x.poste) for x in personnes] == [
        ("urn:li:fsd_profile:factice-1", "Prénom1", "Test", "DRH chez Entreprise Test 1"),
        ("urn:li:fsd_profile:factice-3", "Prénom3", "Test", "Responsable RSE"),
    ]
    assert (personnes[0].url, personnes[0].entreprise) == ("https://www.linkedin.com/in/prenom1-test/",
                                                           "Entreprise Test 1")


def test_connectsafely_profil_ignore_les_dates_illisibles(horloge):
    p = _cs(lambda r: httpx.Response(200, json={"success": True, "posts": [
        {"content": "Récent", "timestamp": "3h"}, {"content": "Sans date"},
        {"content": "Illisible", "timestamp": "hier"}, {"content": "Limite", "timestamp": "5w"}]}))
    assert p.profil("urn:li:fsd_profile:factice-1").posts_recents == [
        (horloge.t - dt.timedelta(hours=3), "Récent")]


def test_connectsafely_etat_compte():
    recues = []

    def compte(**champs):
        etat = {"id": "compte-test", "status": "AVAILABLE", "enabled": True, "hasTokens": True, **champs}
        return lambda r: recues.append(r) or httpx.Response(200, json=etat)
    assert _cs(compte()).etat_compte() == "ok"
    assert _cs(compte(status="IN_USE")).etat_compte() == "ok"
    for champs in ({"status": "ERROR"}, {"enabled": False}, {"hasTokens": False}):
        assert _cs(compte(**champs)).etat_compte() == "a_reconnecter"
    assert _cs(lambda r: httpx.Response(401)).etat_compte() == "a_reconnecter"
    assert str(recues[0].url) == "https://api.connectsafely.ai/linkedin/account/compte-test/status"


def test_connectsafely_webhook_autre_compte_ou_evenement_ignore(horloge):
    p = _cs(lambda r: httpx.Response(500))
    ts = str(calendar.timegm(horloge.t.timetuple()))

    def signe(corps: bytes) -> dict[str, str]:
        return {"X-Webhook-Signature": "sha256=" + hmac.new(b"secret-cs", corps, hashlib.sha256).hexdigest(),
                "X-Webhook-Timestamp": ts}
    autre_compte = json.dumps({"event": "message.received", "data": {
        "message_urn": "urn:li:messagingMessage:test-9", "account_id": "autre-compte",
        "sender": {"id": "urn:li:fsd_profile:factice-1"}, "body": "Bonjour"}}).encode()
    inconnu = json.dumps({"event": "connection.accepted", "data": {"account_id": "compte-test"}}).encode()
    for corps in (autre_compte, inconnu):
        [ev] = p.analyser_webhook(signe(corps), corps)
        assert (ev.type, ev.provider_id) == ("autre", None)
    with pytest.raises(SignatureInvalide):
        p.analyser_webhook(signe(b"pas du json"), b"pas du json")
    with pytest.raises(SignatureInvalide):
        _cs(lambda r: httpx.Response(500), secret="").analyser_webhook(signe(inconnu), inconnu)
