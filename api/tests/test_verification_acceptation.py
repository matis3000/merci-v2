"""Lot L5b : ConnectSafely n'a pas de webhook « invitation acceptée ». Le tick vérifie la relation
des invitations en attente (20 profils au plus par passage) et applique le traitement du webhook."""
from __future__ import annotations

import httpx
import pytest
from sqlmodel import select

from app import temps
from app.fournisseurs.base import ErreurFournisseur, EvenementLinkedIn
from app.fournisseurs.linkedin_connectsafely import ConnectSafelyLinkedInProvider
from app.fournisseurs.linkedin_factice import FauxLinkedInProvider
from app.modeles import Activite, Envoi, InscriptionSequence
from app.services import moteur_sequences
from conftest import prospect_inscrit, regler, tick, utiliser_linkedin


class FauxConnectSafely:
    """Transport simulé : invitations et messages acceptés, relation au statut `statut`."""

    def __init__(self, statut: str = "INVITATION_SENT", panne: bool = False):
        self.statut, self.panne = statut, panne
        self.verifications: list[str] = []
        self.actions: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        chemin = req.url.path
        if chemin.startswith("/linkedin/relationship/"):
            self.verifications.append(chemin)
            if self.panne:
                raise httpx.ConnectError("hors ligne", request=req)
            return httpx.Response(200, json={
                "connected": self.statut == "CONNECTED", "invitationSent": self.statut == "INVITATION_SENT",
                "invitationReceived": False, "status": self.statut,
                "profileUrn": "urn:li:fsd_profile:test", "accountId": "compte-test"})
        self.actions.append(chemin.rsplit("/", 1)[-1])
        return httpx.Response(200, json={"success": True})


def _cs(faux: FauxConnectSafely) -> ConnectSafelyLinkedInProvider:
    return ConnectSafelyLinkedInProvider("cle-de-test", "compte-test", transport=httpx.MockTransport(faux))


def _prospect(session, n: int = 1):
    """Prospect inscrit, avec profil public (l'invitation part au premier tick)."""
    c, insc = prospect_inscrit(session, n)
    c.linkedin_url = f"https://www.linkedin.com/in/prenom-test-{n}/"
    session.add(c)
    session.commit()
    return c, insc


def _relire(session, objet):
    session.expire_all()
    return session.get(type(objet), objet.id)


def _acceptees(session, contact_id: int) -> list[Activite]:
    session.expire_all()
    return list(session.exec(select(Activite).where(Activite.contact_id == contact_id,
                                                    Activite.type == "linkedin_acceptee")))


# --------------------------------------------------------------------------- fournisseurs

def test_connectsafely_verifier_acceptation_route_documentee():
    faux = FauxConnectSafely("CONNECTED")
    p = _cs(faux)
    assert p.verifier_acceptation("urn:li:fsd_profile:test", "https://www.linkedin.com/in/prenom-test-1/") is True
    assert faux.verifications == ["/linkedin/relationship/compte-test/prenom-test-1"]
    for statut in ("INVITATION_SENT", "INVITATION_RECEIVED", "NOT_CONNECTED"):
        faux.statut = statut
        assert p.verifier_acceptation("urn", "https://www.linkedin.com/in/prenom-test-1") is False
    assert p.verifier_acceptation("urn", None) is None            # sans profil public : non vérifiable
    faux.panne = True
    with pytest.raises(ErreurFournisseur):
        p.verifier_acceptation("urn", "https://www.linkedin.com/in/prenom-test-1")


def test_factice_ne_verifie_rien(tmp_path):
    assert FauxLinkedInProvider(dossier=tmp_path).verifier_acceptation("factice-personne-1", None) is None


# --------------------------------------------------------------------------- tick

def test_acceptation_detectee_traitee_comme_le_webhook(client, session, horloge):
    faux = FauxConnectSafely()
    utiliser_linkedin(_cs(faux))
    c, insc = _prospect(session)
    assert tick(client).json()["envoyes"] == 1
    assert faux.actions == ["connect"] and faux.verifications == []
    envoi = session.exec(select(Envoi).where(Envoi.inscription_id == insc.id)).one()
    assert envoi.fournisseur == "connectsafely"
    horloge.avancer(days=1)
    faux.statut = "CONNECTED"
    r = tick(client).json()
    assert faux.verifications == ["/linkedin/relationship/compte-test/prenom-test-1"]
    assert r["envoyes"] == 1 and faux.actions == ["connect", "message"]  # pas 2 parti dans le même tick
    assert _relire(session, envoi).accepte_at == horloge.t
    insc = _relire(session, insc)
    assert insc.ancre_at == horloge.t and insc.pas_courant == 3
    assert [a.titre for a in _acceptees(session, c.id)] == ["Invitation acceptée"]
    horloge.avancer(hours=1)
    tick(client)
    assert len(faux.verifications) == 1 and len(_acceptees(session, c.id)) == 1


def test_invitation_non_acceptee_reste_en_attente(client, session, horloge):
    faux = FauxConnectSafely("INVITATION_SENT")
    utiliser_linkedin(_cs(faux))
    c, insc = _prospect(session)
    tick(client)
    horloge.avancer(days=1)
    assert tick(client).json()["envoyes"] == 0
    assert len(faux.verifications) == 1
    insc = _relire(session, insc)
    assert (insc.statut, insc.pas_courant, insc.prochain_envoi_at) == ("active", 2, None)
    assert _acceptees(session, c.id) == []
    assert session.exec(select(Envoi.accepte_at).where(Envoi.inscription_id == insc.id)).one() is None


def test_erreur_reseau_sans_effet_de_bord(client, session, horloge):
    faux = FauxConnectSafely("CONNECTED")
    utiliser_linkedin(_cs(faux))
    c, insc = _prospect(session)
    tick(client)
    envoi = session.exec(select(Envoi).where(Envoi.inscription_id == insc.id)).one()
    avant = (envoi.statut, envoi.essais, envoi.maj_at, envoi.accepte_at)
    horloge.avancer(days=1)
    faux.panne = True
    r = tick(client)
    assert r.status_code == 200 and r.json()["statut"] == "fait" and r.json()["envoyes"] == 0
    assert len(faux.verifications) == 1
    envoi = _relire(session, envoi)
    assert (envoi.statut, envoi.essais, envoi.maj_at, envoi.accepte_at) == avant
    insc = _relire(session, insc)
    assert (insc.statut, insc.pas_courant, insc.prochain_envoi_at) == ("active", 2, None)
    assert _acceptees(session, c.id) == [] and faux.actions == ["connect"]


def test_pas_de_double_traitement_si_le_webhook_est_passe(client, session, horloge):
    faux = FauxConnectSafely("CONNECTED")
    utiliser_linkedin(_cs(faux))
    c, insc = _prospect(session)
    tick(client)
    horloge.avancer(days=1)
    ev = EvenementLinkedIn(cle="relation:test-1", type="invitation_acceptee", provider_id=c.linkedin_provider_id,
                           texte=None, recu_at=temps.maintenant())
    assert moteur_sequences.traiter_evenement_linkedin(session, ev, "connectsafely") is True
    session.commit()
    tick(client)
    tick(client)
    assert faux.verifications == []  # déjà acceptée : plus rien à vérifier
    assert len(_acceptees(session, c.id)) == 1


def test_au_plus_20_verifications_par_passage_puis_rotation(client, session, horloge):
    regler(session, prospection_plafond_jour=50)
    faux = FauxConnectSafely("INVITATION_SENT")
    utiliser_linkedin(_cs(faux))
    for n in range(1, 22):
        _prospect(session, n)
    assert tick(client).json()["envoyes"] == 21
    horloge.avancer(days=1)
    tick(client)
    assert len(faux.verifications) == moteur_sequences.VERIFICATIONS_PAR_TICK == 20
    premiers = set(faux.verifications)
    horloge.avancer(hours=1)
    tick(client)
    assert faux.verifications[20] not in premiers  # le profil pas encore vérifié passe en premier


def test_seulement_les_invitations_de_ce_fournisseur(client, session, horloge, tmp_path):
    """Une invitation partie par un autre fournisseur n'est pas vérifiée par ConnectSafely."""
    utiliser_linkedin(FauxLinkedInProvider(dossier=tmp_path / "li"))
    c, insc = _prospect(session)
    tick(client)
    faux = FauxConnectSafely("CONNECTED")
    utiliser_linkedin(_cs(faux))
    horloge.avancer(days=1)
    tick(client)
    assert faux.verifications == [] and _acceptees(session, c.id) == []
    assert session.exec(select(InscriptionSequence.pas_courant).where(InscriptionSequence.id == insc.id)).one() == 2
