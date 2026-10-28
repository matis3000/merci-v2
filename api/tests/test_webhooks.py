"""Webhooks Resend : signature Svix, anti-rejeu, effets des événements (section 4.12)."""
from __future__ import annotations

import base64
import calendar
import hashlib
import hmac
import json

import httpx
from sqlmodel import select

from app.fournisseurs.email_resend import ResendEmailProvider
from app.modeles import Activite, Contact, Envoi, InscriptionSequence
from conftest import donateur_inscrit, regler, tick, utiliser_email

SECRET = "whsec_" + base64.b64encode(b"secret-webhook-de-test-0123456789").decode()


def _resend():
    compteur = [0]

    def repondre(request: httpx.Request) -> httpx.Response:
        compteur[0] += 1
        return httpx.Response(200, json={"id": f"re-test-{compteur[0]}"})
    return ResendEmailProvider("re_cle_de_test", SECRET, transport=httpx.MockTransport(repondre))


def _signer(corps: bytes, ident: str, horodatage: int) -> dict[str, str]:
    cle = base64.b64decode(SECRET.removeprefix("whsec_"))
    mac = hmac.new(cle, f"{ident}.{horodatage}.".encode() + corps, hashlib.sha256).digest()
    return {"svix-id": ident, "svix-timestamp": str(horodatage),
            "svix-signature": f"v1,{base64.b64encode(mac).decode()}", "content-type": "application/json"}


def _epoch(horloge) -> int:
    return calendar.timegm(horloge.t.timetuple())


def _evenement(client, horloge, type_: str, email_id: str, ident: str, decalage: int = 0, signature=None):
    corps = json.dumps({"type": type_, "created_at": "2026-10-12T08:00:00Z",
                        "data": {"email_id": email_id, "to": ["prenom@exemple.test"]}}).encode()
    entetes = _signer(corps, ident, _epoch(horloge) + decalage)
    if signature is not None:
        entetes["svix-signature"] = signature
    return client.post("/webhooks/resend", content=corps, headers=entetes)


def _envoye(client, session, horloge):
    utiliser_email(_resend())
    c, insc = donateur_inscrit(session)
    assert tick(client).json()["envoyes"] == 1
    envoi = session.exec(select(Envoi).where(Envoi.inscription_id == insc.id)).one()
    assert envoi.fournisseur == "resend" and envoi.fournisseur_id.startswith("re-test-")
    return c, insc, envoi


def _activites(session, type_):
    session.expire_all()
    return list(session.exec(select(Activite).where(Activite.type == type_)))


def test_resend_signature_invalide_401(client, session, horloge):
    utiliser_email(_resend())
    r = _evenement(client, horloge, "email.opened", "re-x", "msg_1", signature="v1,ZmF1c3Nl")
    assert r.status_code == 401
    r = client.post("/webhooks/resend", content=b"{}", headers={"content-type": "application/json"})
    assert r.status_code == 401


def test_resend_horodatage_trop_ancien_401(client, session, horloge):
    utiliser_email(_resend())
    assert _evenement(client, horloge, "email.opened", "re-x", "msg_1", decalage=-301).status_code == 401
    assert _evenement(client, horloge, "email.opened", "re-x", "msg_2", decalage=-60).status_code == 200


def test_resend_ouvert_journalise_une_fois(client, session, horloge):
    _, _, envoi = _envoye(client, session, horloge)
    t1 = horloge.t
    assert _evenement(client, horloge, "email.delivered", envoi.fournisseur_id, "msg_0").json() == {"ok": True}
    assert _evenement(client, horloge, "email.opened", envoi.fournisseur_id, "msg_1").status_code == 200
    horloge.avancer(minutes=3)
    assert _evenement(client, horloge, "email.opened", envoi.fournisseur_id, "msg_2").status_code == 200
    session.refresh(envoi)
    assert envoi.ouvert_at == t1 and envoi.delivre_at == t1
    assert len(_activites(session, "email_ouvert")) == 1
    assert len(_activites(session, "email_delivre")) == 1


def test_resend_rebond_met_la_sequence_en_echec(client_connecte, session, horloge):
    c, insc, envoi = _envoye(client_connecte, session, horloge)
    _evenement(client_connecte, horloge, "email.bounced", envoi.fournisseur_id, "msg_1")
    session.expire_all()
    insc = session.get(InscriptionSequence, insc.id)
    assert (insc.statut, insc.raison_arret) == ("echec", "rebond")
    assert len(_activites(session, "email_rebond")) == 1
    [a_faire] = client_connecte.get("/accueil").json()["a_faire"]
    assert a_faire["type"] == "echec" and a_faire["titre"].startswith("E-mail en rebond pour")


def test_resend_plainte_desinscrit(client, session, horloge):
    regler(session, lien_creation_compte="https://app.exemple.test/compte")
    utiliser_email(_resend())
    c, _ = donateur_inscrit(session, sequence="donateur-pilote", etape="pilote_ouvert")
    tick(client)
    envoi = session.exec(select(Envoi)).one()
    _evenement(client, horloge, "email.complained", envoi.fournisseur_id, "msg_1")
    session.expire_all()
    assert session.get(Contact, c.id).desinscrit_at == horloge.t
    insc = session.exec(select(InscriptionSequence)).one()
    assert (insc.statut, insc.raison_arret) == ("arretee", "plainte")
    assert len(_activites(session, "email_plainte")) == 1


def test_resend_evenement_rejoue_ignore(client, session, horloge):
    _, _, envoi = _envoye(client, session, horloge)
    for _ in range(2):
        r = _evenement(client, horloge, "email.clicked", envoi.fournisseur_id, "msg_meme")
        assert r.status_code == 200 and r.json() == {"ok": True}
    assert len(_activites(session, "email_clique")) == 1


def test_resend_type_ignore_et_email_inconnu_200(client, session, horloge):
    utiliser_email(_resend())
    assert _evenement(client, horloge, "email.sent", "re-inconnu", "msg_1").json() == {"ok": True}
    assert _evenement(client, horloge, "email.opened", "re-inconnu", "msg_2").json() == {"ok": True}
    assert _activites(session, "email_ouvert") == []


# --------------------------------------------------------------------------- LinkedIn (lot L5), ConnectSafely simulé

from pathlib import Path  # noqa: E402

from app.fournisseurs.linkedin_connectsafely import ConnectSafelyLinkedInProvider  # noqa: E402
from app.fournisseurs.linkedin_factice import FauxLinkedInProvider  # noqa: E402
from app.modeles import Affaire, Reglage  # noqa: E402
from conftest import prospect_inscrit, utiliser_linkedin  # noqa: E402

EVTS = json.loads((Path(__file__).parent / "fixtures" / "connectsafely_evenements.json").read_text())
SECRET_LI = "secret-linkedin-de-test-0123456789"


def _connectsafely(secret: str = SECRET_LI) -> ConnectSafelyLinkedInProvider:
    def interdit(request):
        raise AssertionError("aucun appel sortant attendu pendant un webhook")
    return ConnectSafelyLinkedInProvider("cle-connectsafely-test", "compte-test", secret_webhook=secret,
                                         transport=httpx.MockTransport(interdit))


def _webhook_li(client, horloge, nom: str, secret: str | None = SECRET_LI, decalage: int = 0):
    """Événement de la fixture signé comme ConnectSafely : HMAC-SHA256 du corps brut, horodatage en secondes."""
    utiliser_linkedin(_connectsafely())
    corps = json.dumps(EVTS[nom]).encode()
    entetes = {"content-type": "application/json", "X-Webhook-Timestamp": str(_epoch(horloge) + decalage)}
    if secret is not None:
        entetes["X-Webhook-Signature"] = "sha256=" + hmac.new(secret.encode(), corps, hashlib.sha256).hexdigest()
    return client.post("/webhooks/linkedin", content=corps, headers=entetes)


def _webhook_normalise(client, *evenements: dict):
    """Fournisseur factice (développement) : événements normalisés que ConnectSafely n'émet pas."""
    utiliser_linkedin(FauxLinkedInProvider())
    return client.post("/webhooks/linkedin", content=json.dumps({"evenements": list(evenements)}).encode(),
                       headers={"content-type": "application/json"})


def _invitation_envoyee(client, session):
    """Prospect dont l'invitation (pas 1) est partie par le fournisseur factice."""
    c, insc = prospect_inscrit(session)
    assert tick(client).json()["envoyes"] == 1
    return c, insc


def test_linkedin_signature_invalide_401(client, session, horloge):
    assert _webhook_li(client, horloge, "message_recu", secret="mauvais-secret").status_code == 401
    assert _webhook_li(client, horloge, "message_recu", secret=None).status_code == 401
    assert _webhook_li(client, horloge, "message_recu", decalage=-301).status_code == 401
    utiliser_linkedin(_connectsafely(secret=""))
    corps = json.dumps(EVTS["message_recu"]).encode()
    r = client.post("/webhooks/linkedin", content=corps,
                    headers={"X-Webhook-Signature": "sha256=" + hmac.new(b"", corps, hashlib.sha256).hexdigest(),
                             "X-Webhook-Timestamp": str(_epoch(horloge))})
    assert r.status_code == 401
    assert _webhook_li(client, horloge, "message_recu", decalage=-60).status_code == 200


def test_linkedin_reponse_arrete_la_sequence_et_passe_a_repondu(client_connecte, session, horloge):
    c, insc = _invitation_envoyee(client_connecte, session)
    r = _webhook_li(client_connecte, horloge, "message_recu")
    assert (r.status_code, r.json()) == (200, {"ok": True, "traites": 1})
    session.expire_all()
    insc = session.get(InscriptionSequence, insc.id)
    assert (insc.statut, insc.raison_arret) == ("arretee", "reponse")
    affaire = session.exec(select(Affaire).where(Affaire.contact_id == c.id)).one()
    assert affaire.etape == "a_repondu"
    [reponse] = _activites(session, "linkedin_reponse")
    assert reponse.texte == "Bonjour, volontiers pour une démo la semaine prochaine."
    fil = client_connecte.get(f"/contacts/{c.id}").json()["activites"]
    assert any(a["type"] == "linkedin_reponse" and a["fort"] for a in fil)
    a_faire = client_connecte.get("/accueil").json()["a_faire"][0]
    assert (a_faire["type"], a_faire["titre"]) == ("reponse", "Prénom1 a répondu sur LinkedIn")
    # Rejeu du même message : sans effet.
    assert _webhook_li(client_connecte, horloge, "message_recu").json() == {"ok": True, "traites": 0}
    assert len(_activites(session, "linkedin_reponse")) == 1


def test_linkedin_message_d_un_autre_compte_ignore(client, session, horloge):
    c, insc = _invitation_envoyee(client, session)
    for nom in ("message_autre_compte", "message_expediteur_inconnu", "evenement_non_gere"):
        r = _webhook_li(client, horloge, nom)
        assert (r.status_code, r.json()) == (200, {"ok": True, "traites": 0}), nom
    session.expire_all()
    assert session.get(InscriptionSequence, insc.id).statut == "active"
    assert _activites(session, "linkedin_reponse") == []


def test_linkedin_acceptation_planifie_le_message(client, session, horloge):
    # ConnectSafely n'émet pas d'événement « invitation acceptée » (le tick la vérifie, voir
    # test_verification_acceptation) : le traitement de l'événement par la route reste couvert ici.
    c, insc = _invitation_envoyee(client, session)
    horloge.avancer(days=2)
    acceptee = {"cle": "relation:factice-personne-1", "type": "invitation_acceptee", "provider_id": "factice-personne-1"}
    assert _webhook_normalise(client, acceptee).json() == {"ok": True, "traites": 1}
    session.expire_all()
    insc = session.get(InscriptionSequence, insc.id)
    assert (insc.pas_courant, insc.ancre_at, insc.prochain_envoi_at) == (2, horloge.t, horloge.t)
    envoi = session.exec(select(Envoi).where(Envoi.inscription_id == insc.id, Envoi.pas == 1)).one()
    assert envoi.accepte_at == horloge.t
    assert len(_activites(session, "linkedin_acceptee")) == 1
    # Une relation sans invitation de notre part : rien.
    inconnue = dict(acceptee, cle="relation:factice-inconnu", provider_id="factice-inconnu")
    assert _webhook_normalise(client, inconnue).json() == {"ok": True, "traites": 0}


def test_linkedin_compte_deconnecte_affiche_le_bandeau(client_connecte, session, horloge):
    # Pas d'événement d'état de compte chez ConnectSafely (etat_compte est interrogé) : événement normalisé.
    assert _webhook_normalise(client_connecte, {"cle": "statut:1", "type": "compte_deconnecte"}).json() == {
        "ok": True, "traites": 1}
    session.expire_all()
    r = session.get(Reglage, 1)
    assert (r.linkedin_etat, r.linkedin_etat_at) == ("a_reconnecter", horloge.t)
    assert client_connecte.get("/coque").json()["linkedin"]["etat"] == "a_reconnecter"
    horloge.avancer(minutes=10)
    _webhook_normalise(client_connecte, {"cle": "statut:2", "type": "compte_ok"})
    assert client_connecte.get("/coque").json()["linkedin"]["etat"] == "ok"
