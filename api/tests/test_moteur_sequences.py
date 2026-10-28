"""Moteur de séquences : tick, créneau, pauses, idempotence, erreurs, arrêts, pilote (section 5)."""
from __future__ import annotations

import datetime as dt

from sqlmodel import select

from app import temps, verrou
from app.fournisseurs.base import ErreurFournisseur
from app.modeles import Activite, Affaire, Envoi, InscriptionSequence, Reglage
from app.services import moteur_sequences
from conftest import (
    CLES_PASDEF, CLES_SEQUENCEDEF, connecter, creer_contact, creer_organisation, donateur_inscrit, entreprise_inscrite,
    lire_emails, prospect_inscrit, regler, tick, utiliser_email, utiliser_linkedin,
)

CLES_TICK = {"statut", "traites", "envoyes", "erreurs", "echecs", "sautes", "en_attente", "duree_ms"}


class EmailEnPanne:
    """Échoue `pannes` fois, puis délègue à la boîte locale."""
    nom = "console"

    def __init__(self, suite, pannes: int = 99):
        self.suite, self.pannes, self.appels = suite, pannes, 0

    def envoyer(self, msg):
        self.appels += 1
        if self.appels <= self.pannes:
            raise ErreurFournisseur("Fournisseur indisponible : HTTP 503")
        return self.suite.envoyer(msg)

    def analyser_webhook(self, entetes, corps):
        return []


def _envois(session, insc_id):
    session.expire_all()
    return list(session.exec(select(Envoi).where(Envoi.inscription_id == insc_id).order_by(Envoi.pas)))


def _relire(session, objet):
    session.expire_all()
    return session.get(type(objet), objet.id)


# --------------------------------------------------------------------------- tick, idempotence

def test_tick_secret_invalide_401(client):
    assert client.post("/cron/tick").status_code == 401
    assert tick(client, secret="mauvais-secret").status_code == 401


def test_tick_envoie_le_pas_du(client, session, horloge, fournisseurs_factices):
    c, insc = donateur_inscrit(session)
    r = tick(client)
    assert r.status_code == 200
    corps = r.json()
    assert set(corps) == CLES_TICK
    assert set(corps["en_attente"]) == {"plafond", "linkedin_deconnecte"}
    assert (corps["statut"], corps["traites"], corps["envoyes"], corps["erreurs"]) == ("fait", 1, 1, 0)
    [mail] = lire_emails(fournisseurs_factices)
    assert mail["a"] == "prenom@exemple.test" and mail["sujet"] == "Bienvenue chez MERCI"
    assert "Prénom Test" in mail["texte"] and "Valentin, de MERCI" in mail["texte"]
    [envoi] = _envois(session, insc.id)
    assert (envoi.statut, envoi.essais, envoi.fournisseur, envoi.envoye_at) == ("envoye", 1, "console", horloge.t)
    assert envoi.fournisseur_id == mail["id"]
    insc = _relire(session, insc)
    assert (insc.statut, insc.pas_courant, insc.prochain_envoi_at) == ("terminee", 2, None)
    types = [a.type for a in session.exec(select(Activite).where(Activite.contact_id == c.id))]
    assert "email_envoye" in types and "sequence_terminee" in types


def test_idempotence_deux_ticks_un_seul_envoi(client, session, horloge, fournisseurs_factices):
    donateur_inscrit(session)
    assert tick(client).json()["envoyes"] == 1
    horloge.avancer(minutes=5)
    assert tick(client).json()["envoyes"] == 0
    assert len(fournisseurs_factices.emails()) == 1


def test_idempotence_tick_et_envoi_immediat_concurrents(client, session, horloge, fournisseurs_factices):
    """Pendant l'appel au fournisseur, un second processus tente le même pas : il trouve la
    réservation et s'arrête sans appel fournisseur."""
    _, insc = donateur_inscrit(session)

    class Concurrent:
        nom = "console"

        def __init__(self):
            self.appels = 0

        def envoyer(self, msg):
            self.appels += 1
            if self.appels == 1:
                moteur_sequences.executer_pas(insc.id, self)
            return fournisseurs_factices.email.envoyer(msg)

    concurrent = Concurrent()
    utiliser_email(concurrent)
    assert tick(client).json()["envoyes"] == 1
    assert concurrent.appels == 1
    assert len(fournisseurs_factices.emails()) == 1
    moteur_sequences.executer_pas(insc.id, concurrent)  # après coup : rien de plus
    assert concurrent.appels == 1 and len(_envois(session, insc.id)) == 1


# --------------------------------------------------------------------------- créneau

def test_creneau_samedi_rien_ne_part(client, session, horloge, fournisseurs_factices):
    horloge.avancer(days=5)  # samedi 17/10/2026, 10 h à Paris
    _, insc = donateur_inscrit(session)
    assert tick(client).json()["statut"] == "hors_creneau"
    assert fournisseurs_factices.emails() == []
    moteur_sequences.executer_pas(insc.id, fournisseurs_factices.email)
    assert fournisseurs_factices.emails() == [] and _envois(session, insc.id) == []


def test_creneau_lundi_8h59_rien_9h00_part(client, session, horloge, fournisseurs_factices):
    horloge.t = dt.datetime(2026, 10, 12, 6, 59)  # 8 h 59 à Paris (heure d'été)
    donateur_inscrit(session)
    assert tick(client).json()["statut"] == "hors_creneau"
    horloge.t = dt.datetime(2026, 10, 12, 7, 0)
    assert tick(client).json()["envoyes"] == 1


def test_creneau_17h59_part_18h00_attend(client, session, horloge, fournisseurs_factices):
    horloge.t = dt.datetime(2026, 10, 12, 15, 59)  # 17 h 59 à Paris
    donateur_inscrit(session)
    assert tick(client).json()["envoyes"] == 1
    horloge.t = dt.datetime(2026, 10, 12, 16, 0)  # 18 h 00
    donateur_inscrit(session, email="autre@exemple.test")
    assert tick(client).json()["statut"] == "hors_creneau"
    assert len(fournisseurs_factices.emails()) == 1


def test_creneau_heure_ete_et_heure_hiver(client, session, horloge, fournisseurs_factices):
    r = session.get(Reglage, 1)
    # Été (UTC+2) : 7 h UTC = 9 h à Paris. Hiver (UTC+1) : 7 h 30 UTC = 8 h 30, 8 h UTC = 9 h.
    assert temps.dans_creneau(dt.datetime(2026, 10, 12, 7, 0), r)
    assert not temps.dans_creneau(dt.datetime(2026, 11, 2, 7, 30), r)
    assert temps.dans_creneau(dt.datetime(2026, 11, 2, 8, 0), r)
    horloge.t = dt.datetime(2026, 11, 2, 7, 30)  # lundi, heure d'hiver
    donateur_inscrit(session)
    assert tick(client).json()["statut"] == "hors_creneau"
    horloge.t = dt.datetime(2026, 11, 2, 8, 0)
    assert tick(client).json()["envoyes"] == 1


# --------------------------------------------------------------------------- pauses, coupure

def test_pause_generale_rien_ne_part_puis_reprise_au_meme_pas(client_connecte, session, horloge,
                                                              fournisseurs_factices):
    _, insc = donateur_inscrit(session)
    assert client_connecte.patch("/reglages", json={"relances_en_pause": True}).status_code == 200
    assert tick(client_connecte).json()["statut"] == "pause"
    moteur_sequences.executer_pas(insc.id, fournisseurs_factices.email)
    assert fournisseurs_factices.emails() == []
    insc = _relire(session, insc)
    assert (insc.statut, insc.pas_courant) == ("active", 1)
    horloge.avancer(days=2)
    client_connecte.patch("/reglages", json={"relances_en_pause": False})
    assert tick(client_connecte).json()["envoyes"] == 1
    assert [e.pas for e in _envois(session, insc.id)] == [1]


def test_pause_individuelle_bloque_seulement_ce_contact(client_connecte, session, horloge, fournisseurs_factices):
    c1, insc1 = donateur_inscrit(session)
    donateur_inscrit(session, email="autre@exemple.test")
    assert client_connecte.post(f"/contacts/{c1.id}/pause", json={"pause": True}).status_code == 200
    assert tick(client_connecte).json()["envoyes"] == 1
    assert [m["a"] for m in lire_emails(fournisseurs_factices)] == ["autre@exemple.test"]
    moteur_sequences.executer_pas(insc1.id, fournisseurs_factices.email)
    assert _envois(session, insc1.id) == []


def test_sequence_coupee_ne_part_pas(client_connecte, session, horloge, fournisseurs_factices):
    _, insc = donateur_inscrit(session)
    r = client_connecte.patch("/sequences/donateur-bienvenue", json={"coupee": True})
    assert r.status_code == 200 and r.json()["coupee"] is True
    assert tick(client_connecte).json()["envoyes"] == 0
    moteur_sequences.executer_pas(insc.id, fournisseurs_factices.email)
    assert fournisseurs_factices.emails() == []
    client_connecte.patch("/sequences/donateur-bienvenue", json={"coupee": False})
    assert tick(client_connecte).json()["envoyes"] == 1


# --------------------------------------------------------------------------- erreurs, verrou, ménage

def test_erreur_puis_succes_au_tick_suivant(client, session, horloge, fournisseurs_factices):
    _, insc = donateur_inscrit(session)
    utiliser_email(EmailEnPanne(fournisseurs_factices.email, pannes=1))
    assert tick(client).json()["erreurs"] == 1
    [envoi] = _envois(session, insc.id)
    assert (envoi.statut, envoi.essais) == ("erreur", 1) and "503" in envoi.derniere_erreur
    horloge.avancer(minutes=5)
    assert tick(client).json()["envoyes"] == 1
    [envoi] = _envois(session, insc.id)
    assert (envoi.statut, envoi.essais) == ("envoye", 2)
    assert len(fournisseurs_factices.emails()) == 1


def test_trois_essais_puis_echec_visible_dans_accueil(client_connecte, session, horloge, fournisseurs_factices):
    c, insc = donateur_inscrit(session)
    utiliser_email(EmailEnPanne(fournisseurs_factices.email))
    for _ in range(3):
        tick(client_connecte)
        horloge.avancer(minutes=5)
    assert tick(client_connecte).json()["traites"] == 0
    [envoi] = _envois(session, insc.id)
    assert (envoi.statut, envoi.essais) == ("echec", 3)
    insc = _relire(session, insc)
    assert (insc.statut, insc.raison_arret) == ("echec", "trois_essais")
    a_faire = client_connecte.get("/accueil").json()["a_faire"]
    assert [(f["type"], f["cible"]["id"]) for f in a_faire] == [("echec", c.id)]
    assert client_connecte.get("/coque").json()["nb_echecs"] == 1


def test_verrou_empeche_double_tick(client, session, horloge, fournisseurs_factices):
    donateur_inscrit(session)
    assert verrou.prendre(session, "tick", dt.timedelta(minutes=10))
    assert tick(client).json()["statut"] == "verrouille"
    assert fournisseurs_factices.emails() == []


def test_verrou_expire_repris(client, session, horloge, fournisseurs_factices):
    donateur_inscrit(session)
    assert verrou.prendre(session, "tick", dt.timedelta(minutes=10))
    horloge.avancer(minutes=11)
    assert tick(client).json()["envoyes"] == 1
    assert tick(client).json()["statut"] == "fait"  # relâché après le tick


def test_envoi_en_cours_ancien_devient_incertain_sans_renvoi(client, session, horloge, fournisseurs_factices):
    _, insc = donateur_inscrit(session)
    t = horloge.t
    session.add(Envoi(inscription_id=insc.id, pas=1, canal="email", statut="en_cours", essais=1,
                      cree_at=t, maj_at=t))
    session.commit()
    horloge.avancer(minutes=31)
    tick(client)
    [envoi] = _envois(session, insc.id)
    assert envoi.statut == "incertain"
    insc = _relire(session, insc)
    assert (insc.statut, insc.raison_arret) == ("echec", "envoi_incertain")
    assert fournisseurs_factices.emails() == []
    assert session.exec(select(Activite).where(Activite.type == "sequence_echec")).first() is not None


# --------------------------------------------------------------------------- étapes, sauts, arrêts

def test_bienvenue_envoyee_change_l_etape(client, session, horloge, fournisseurs_factices):
    c, _ = donateur_inscrit(session)
    tick(client)
    session.expire_all()
    affaire = session.exec(select(Affaire).where(Affaire.contact_id == c.id)).one()
    assert affaire.etape == "bienvenue_envoyee"


def test_entreprise_entrante_pas_1_passe_en_contacte(client, session, horloge, fournisseurs_factices):
    c, insc = entreprise_inscrite(session)  # aucun lien de rendez-vous requis : on propose de répondre
    assert tick(client).json()["envoyes"] == 1
    [mail] = lire_emails(fournisseurs_factices)
    assert mail["sujet"] == "Merci pour votre intérêt, Prénom Test"
    assert "créneaux" in mail["texte"] and "Valentin, de MERCI" in mail["texte"]
    session.expire_all()
    affaire = session.exec(select(Affaire).where(Affaire.contact_id == c.id)).one()
    assert affaire.etape == "contacte"
    insc = _relire(session, insc)
    assert (insc.pas_courant, insc.prochain_envoi_at) == (2, insc.cree_at + dt.timedelta(days=3))


def test_pas_linkedin_saute_si_profil_inconnu(client, session, horloge, fournisseurs_factices):
    _, insc = entreprise_inscrite(session)
    insc.pas_courant, insc.prochain_envoi_at = 3, horloge.t
    session.add(insc)
    session.commit()
    assert tick(client).json()["sautes"] == 1
    [envoi] = _envois(session, insc.id)
    assert (envoi.pas, envoi.statut) == (3, "saute")
    assert _relire(session, insc).statut == "terminee"


def test_pas_email_saute_si_adresse_inconnue(client, session, horloge, fournisseurs_factices):
    _, insc = entreprise_inscrite(session, email=None, sequence="entreprise-prospection",
                                  linkedin_provider_id="factice-personne-1")
    insc.pas_courant, insc.prochain_envoi_at = 4, horloge.t
    session.add(insc)
    session.commit()
    assert tick(client).json()["sautes"] == 1
    [envoi] = _envois(session, insc.id)
    assert (envoi.pas, envoi.statut) == (4, "saute")
    assert _relire(session, insc).statut == "terminee"
    assert fournisseurs_factices.emails() == []


def test_changement_etape_manuel_arrete_la_sequence(client_connecte, session, horloge, fournisseurs_factices):
    c, insc = donateur_inscrit(session)
    affaire = session.exec(select(Affaire).where(Affaire.contact_id == c.id)).one()
    r = client_connecte.patch(f"/affaires/{affaire.id}", json={"etape": "pilote_ouvert"})
    assert r.status_code == 200
    insc = _relire(session, insc)
    assert (insc.statut, insc.raison_arret) == ("arretee", "etape_changee")
    assert tick(client_connecte).json()["envoyes"] == 0
    assert fournisseurs_factices.emails() == []


def test_passage_en_perdu_arrete_la_sequence(client_connecte, session, horloge, fournisseurs_factices):
    c, insc = donateur_inscrit(session)
    affaire = session.exec(select(Affaire).where(Affaire.contact_id == c.id)).one()
    client_connecte.patch(f"/affaires/{affaire.id}", json={"etape": "perdu", "perdue_raison": "Test"})
    insc = _relire(session, insc)
    assert (insc.statut, insc.raison_arret) == ("arretee", "perdu")
    # Contrôle au moment de l'envoi : affaire passée en perdu sans passer par la route.
    c2, insc2 = donateur_inscrit(session, email="autre@exemple.test")
    a2 = session.exec(select(Affaire).where(Affaire.contact_id == c2.id)).one()
    a2.etape = "perdu"
    session.add(a2)
    session.commit()
    tick(client_connecte)
    insc2 = _relire(session, insc2)
    assert (insc2.statut, insc2.raison_arret) == ("arretee", "perdu")
    assert fournisseurs_factices.emails() == []


def test_sans_acceptation_21_jours_terminee(client, session, horloge, fournisseurs_factices):
    _, insc = entreprise_inscrite(session, sequence="entreprise-prospection",
                                  linkedin_provider_id="factice-personne-1")
    t = horloge.t
    session.add(Envoi(inscription_id=insc.id, pas=1, canal="linkedin_invitation", statut="envoye", essais=1,
                      envoye_at=t, cree_at=t, maj_at=t))
    insc.pas_courant, insc.prochain_envoi_at = 2, None
    session.add(insc)
    session.commit()
    horloge.avancer(days=20)
    tick(client)
    assert _relire(session, insc).statut == "active"
    horloge.avancer(days=1, minutes=1)
    tick(client)
    insc = _relire(session, insc)
    assert (insc.statut, insc.raison_arret, insc.prochain_envoi_at) == ("terminee", "sans_acceptation", None)


def test_variable_manquante_met_le_pas_en_erreur(client, session, horloge, fournisseurs_factices):
    from app.modeles import TextePas
    session.add(TextePas(sequence="entreprise-entrante", pas=1, sujet="Démo", corps="Réservez : {lien_rdv}",
                         maj_at=horloge.t))
    session.commit()
    _, insc = entreprise_inscrite(session)  # texte personnalisé avec lien_rdv, absent des réglages
    assert tick(client).json()["erreurs"] == 1
    [envoi] = _envois(session, insc.id)
    assert envoi.statut == "erreur" and "lien_rdv" in envoi.derniere_erreur
    assert fournisseurs_factices.emails() == []
    assert _relire(session, insc).statut == "active"


# --------------------------------------------------------------------------- pilote

def test_ouverture_pilote_inscrit_les_donateurs_et_change_l_etape(client_connecte, session, horloge,
                                                                  fournisseurs_factices):
    regler(session, lien_creation_compte="https://app.exemple.test/compte")
    c1, insc1 = donateur_inscrit(session)                                  # bienvenue encore active
    c2, _ = donateur_inscrit(session, email="deux@exemple.test", etape="bienvenue_envoyee")
    c3, _ = donateur_inscrit(session, email="trois@exemple.test")
    c3.desinscrit_at = horloge.t
    session.add(c3)
    session.commit()
    r = client_connecte.post("/pilote/ouvrir")
    assert r.status_code == 200
    assert r.json() == {"ouvert_at": temps.iso(horloge.t), "inscrits": 2}
    session.expire_all()
    etapes = {a.contact_id: a.etape for a in session.exec(select(Affaire))}
    assert etapes == {c1.id: "pilote_ouvert", c2.id: "pilote_ouvert", c3.id: "inscrit"}
    insc1 = _relire(session, insc1)
    assert (insc1.statut, insc1.raison_arret) == ("arretee", "objectif_atteint")
    pilotes = session.exec(select(InscriptionSequence).where(InscriptionSequence.sequence == "donateur-pilote"))
    assert sorted(i.contact_id for i in pilotes) == [c1.id, c2.id]
    assert session.get(Reglage, 1).pilote_ouvert_at == horloge.t
    tick(client_connecte)
    mails = lire_emails(fournisseurs_factices)
    assert sorted(m["a"] for m in mails) == ["deux@exemple.test", "prenom@exemple.test"]
    assert {m["sujet"] for m in mails} == {"Le pilote est ouvert"}
    assert all("https://app.exemple.test/compte" in m["texte"] for m in mails)


def test_ouverture_pilote_deux_fois_409(client_connecte, membre, client):
    assert client_connecte.post("/pilote/ouvrir").status_code == 200
    assert client_connecte.post("/pilote/ouvrir").status_code == 409
    assert connecter(client, membre).post("/pilote/ouvrir").status_code == 403


# --------------------------------------------------------------------------- écran Séquences

def test_sequences_forme_actifs_et_stats(client_connecte, session, horloge, fournisseurs_factices):
    donateur_inscrit(session)
    donateur_inscrit(session, email="autre@exemple.test")
    tick(client_connecte)
    r = client_connecte.get("/sequences")
    assert r.status_code == 200
    seqs = {s["cle"]: s for s in r.json()}
    assert list(seqs) == ["donateur-bienvenue", "donateur-pilote", "entreprise-entrante", "association-bienvenue",
                          "entreprise-prospection"]
    for s in seqs.values():
        assert set(s) == CLES_SEQUENCEDEF | {"actifs", "stats"}
        assert set(s["stats"]) == {"envoyes", "ouverts", "acceptees", "reponses"}
        assert all(set(p) == CLES_PASDEF for p in s["pas"])
    b = seqs["donateur-bienvenue"]
    assert b["actifs"] == 0 and b["stats"] == {"envoyes": 2, "ouverts": 0, "acceptees": None, "reponses": 0}
    assert seqs["entreprise-prospection"]["stats"]["acceptees"] == 0


def test_textes_par_defaut_sont_de_vrais_messages(client_connecte):
    seqs = {s["cle"]: s for s in client_connecte.get("/sequences").json()}
    invitation = seqs["entreprise-entrante"]["pas"][2]
    relance = seqs["entreprise-prospection"]["pas"][3]
    for pas in (invitation, relance):
        assert not pas["corps"].startswith("Si ")
        assert "{prenom}" in pas["corps"] and "vous" in pas["corps"]
    assert relance["sujet"] and relance["sujet"] != relance["titre"]
    for s in seqs.values():
        for p in s["pas"]:
            assert "\u2014" not in p["corps"] and "\u2013" not in p["corps"]  # pas de tirets longs
            if p["canal"] == "email":
                assert p["corps"].rstrip().endswith("Valentin, de MERCI")


def test_texte_pas_modifie_utilise_puis_remis_par_defaut(client_connecte, session, horloge, fournisseurs_factices):
    r = client_connecte.put("/sequences/donateur-bienvenue/pas/1",
                            json={"sujet": "Bienvenue {prenom}", "corps": "Bonjour {prenom}, texte de test."})
    assert r.status_code == 200
    assert set(r.json()) == CLES_PASDEF and r.json()["personnalise"] is True
    donateur_inscrit(session)
    tick(client_connecte)
    [mail] = lire_emails(fournisseurs_factices)
    assert mail["sujet"] == "Bienvenue Prénom Test"
    assert mail["texte"].startswith("Bonjour Prénom Test, texte de test.")
    r = client_connecte.put("/sequences/donateur-bienvenue/pas/1", json={"corps": ""})
    assert r.json()["personnalise"] is False and r.json()["sujet"] == "Bienvenue chez MERCI"


def test_texte_pas_erreurs_422_et_404(client_connecte):
    put = client_connecte.put
    assert put("/sequences/inconnue/pas/1", json={"corps": "x"}).status_code == 404
    assert put("/sequences/donateur-bienvenue/pas/9", json={"corps": "x"}).status_code == 404
    r = put("/sequences/donateur-bienvenue/pas/1", json={"sujet": "S", "corps": "Bonjour {nom}"})
    assert r.status_code == 422 and "nom" in r.json()["detail"]
    assert put("/sequences/donateur-bienvenue/pas/1", json={"corps": "Sans sujet"}).status_code == 422
    # Invitation : 300 caractères au plus, variables comptées à leur longueur maximale.
    r = put("/sequences/entreprise-entrante/pas/3", json={"corps": "Bonjour {prenom} " + "x" * 230})
    assert r.status_code == 422
    ok = put("/sequences/entreprise-entrante/pas/3", json={"corps": "Bonjour {prenom}, ravi d'échanger."})
    assert ok.status_code == 200
    assert client_connecte.patch("/sequences/inconnue", json={"coupee": True}).status_code == 404


# --------------------------------------------------------------------------- LinkedIn (lot L5)

def _accepter(client, provider_id: str, cle: str = "acceptation-1"):
    """Webhook normalisé du fournisseur factice (développement) : invitation acceptée."""
    corps = {"evenements": [{"cle": cle, "type": "invitation_acceptee", "provider_id": provider_id}]}
    r = client.post("/webhooks/linkedin", json=corps)
    assert r.status_code == 200, r.text
    return r


def _actions(f) -> list[str]:
    return [e["action"] for e in f.linkedin_envois()]


def test_plafond_20_invitations_par_jour(client_connecte, session, horloge, fournisseurs_factices):
    for n in range(1, 22):
        prospect_inscrit(session, n)
    r = tick(client_connecte).json()
    assert (r["envoyes"], r["en_attente"]["plafond"]) == (20, 1)
    assert _actions(fournisseurs_factices) == ["inviter"] * 20
    horloge.avancer(hours=1)
    r = tick(client_connecte).json()
    assert (r["envoyes"], r["en_attente"]["plafond"]) == (0, 1)
    # La 21e reste due, en attente du plafond (forme EtatSequence).
    session.expire_all()
    attente = session.exec(select(InscriptionSequence).where(InscriptionSequence.pas_courant == 1)).one()
    assert len(_envois(session, attente.id)) == 0
    etat = client_connecte.get(f"/contacts/{attente.contact_id}").json()["sequence"]["etat"]
    assert (etat["etat"], etat["attente"]) == ("due", "plafond")


def test_plafond_remis_a_zero_le_lendemain_heure_de_paris(client, session, horloge, fournisseurs_factices):
    for n in range(1, 22):
        prospect_inscrit(session, n)
    assert tick(client).json()["envoyes"] == 20
    horloge.t = dt.datetime(2026, 10, 12, 21, 59)  # 23 h 59 à Paris : encore lundi
    assert moteur_sequences.contexte(session).invitations_aujourdhui == 20
    horloge.t = dt.datetime(2026, 10, 12, 22, 0)   # minuit à Paris : mardi
    assert moteur_sequences.contexte(session).invitations_aujourdhui == 0
    horloge.t = dt.datetime(2026, 10, 13, 7, 0)    # mardi 9 h à Paris
    r = tick(client).json()
    assert (r["envoyes"], r["en_attente"]["plafond"]) == (1, 0)
    assert len(fournisseurs_factices.linkedin_envois()) == 21


def test_linkedin_deconnecte_suspend_linkedin_email_continue(client_connecte, session, horloge,
                                                             fournisseurs_factices):
    regler(session, linkedin_etat="a_reconnecter")
    c, insc = prospect_inscrit(session)
    donateur_inscrit(session)
    r = tick(client_connecte).json()
    assert (r["envoyes"], r["en_attente"]["linkedin_deconnecte"]) == (1, 1)
    assert fournisseurs_factices.linkedin_envois() == [] and len(fournisseurs_factices.emails()) == 1
    insc = _relire(session, insc)
    assert (insc.statut, insc.pas_courant) == ("active", 1) and _envois(session, insc.id) == []
    etat = client_connecte.get(f"/contacts/{c.id}").json()["sequence"]["etat"]
    assert etat["attente"] == "linkedin_deconnecte"
    regler(session, linkedin_etat="ok")
    assert tick(client_connecte).json()["envoyes"] == 1
    assert _actions(fournisseurs_factices) == ["inviter"]


def test_compte_deconnecte_pendant_l_envoi_essai_non_compte(client_connecte, session, horloge,
                                                            fournisseurs_factices, tmp_path):
    from app.fournisseurs.base import CompteLinkedInDeconnecte
    from app.fournisseurs.linkedin_factice import FauxLinkedInProvider
    _, insc = prospect_inscrit(session)
    utiliser_linkedin(FauxLinkedInProvider(dossier=tmp_path / "li",
                                           erreurs={"inviter": CompteLinkedInDeconnecte("ConnectSafely : HTTP 401")}))
    r = tick(client_connecte).json()
    assert r["envoyes"] == 0
    [envoi] = _envois(session, insc.id)
    assert (envoi.statut, envoi.essais, envoi.derniere_erreur) == ("erreur", 0, "ConnectSafely : HTTP 401")
    session.expire_all()
    assert session.get(Reglage, 1).linkedin_etat == "a_reconnecter"
    assert client_connecte.get("/coque").json()["linkedin"]["etat"] == "a_reconnecter"
    assert _relire(session, insc).statut == "active"


def test_prospection_attend_acceptation_puis_message(client_connecte, session, horloge, fournisseurs_factices):
    c, insc = prospect_inscrit(session)
    assert tick(client_connecte).json()["envoyes"] == 1
    [invitation] = fournisseurs_factices.linkedin_envois()
    assert (invitation["action"], invitation["provider_id"]) == ("inviter", "factice-personne-1")
    assert invitation["texte"].startswith("Bonjour Prénom1,") and len(invitation["texte"]) <= 300
    [envoi] = _envois(session, insc.id)
    assert (envoi.canal, envoi.statut, envoi.fournisseur) == ("linkedin_invitation", "envoye", "factice")
    insc = _relire(session, insc)
    assert (insc.pas_courant, insc.prochain_envoi_at) == (2, None)
    session.expire_all()
    affaire = session.exec(select(Affaire).where(Affaire.contact_id == c.id)).one()
    assert affaire.etape == "contacte"
    activite = session.exec(select(Activite).where(Activite.type == "linkedin_invitation")).one()
    assert activite.titre == "Invitation LinkedIn envoyée" and "note de" in activite.texte
    etat = client_connecte.get(f"/contacts/{c.id}").json()["sequence"]["etat"]
    assert (etat["pas"], etat["attente"], etat["prochain_envoi_at"]) == (2, "acceptation", None)
    horloge.avancer(days=1)
    assert tick(client_connecte).json()["traites"] == 0  # rien sans acceptation
    _accepter(client_connecte, "factice-personne-1")
    insc = _relire(session, insc)
    assert (insc.ancre_at, insc.prochain_envoi_at) == (horloge.t, horloge.t)
    assert _envois(session, insc.id)[0].accepte_at == horloge.t
    assert tick(client_connecte).json()["envoyes"] == 1
    message = fournisseurs_factices.linkedin_envois()[-1]
    assert message["action"] == "ecrire" and message["texte"].startswith("Merci d'avoir accepté, Prénom1.")
    assert session.exec(select(Activite).where(Activite.type == "linkedin_message")).first() is not None
    insc = _relire(session, insc)
    assert (insc.pas_courant, insc.prochain_envoi_at) == (3, horloge.t + dt.timedelta(days=4))


def test_prospection_delais_comptes_depuis_acceptation(client_connecte, session, horloge, fournisseurs_factices):
    c, insc = prospect_inscrit(session, email="prenom1@exemple.test")   # aucun lien de rendez-vous requis
    t0 = horloge.t
    tick(client_connecte)                                    # pas 1 : invitation
    horloge.avancer(days=7, hours=1)                         # acceptée le lundi suivant, 11 h à Paris
    t_acc = horloge.t                                        # +4 j : vendredi, +9 j : mercredi
    _accepter(client_connecte, "factice-personne-1")
    tick(client_connecte)                                    # pas 2 : à l'acceptation
    assert _relire(session, insc).prochain_envoi_at == t_acc + dt.timedelta(days=4)
    horloge.t = t_acc + dt.timedelta(days=4)
    tick(client_connecte)                                    # pas 3 : acceptation + 4 j
    insc = _relire(session, insc)
    assert (insc.pas_courant, insc.prochain_envoi_at) == (4, t_acc + dt.timedelta(days=9))
    assert insc.prochain_envoi_at != t0 + dt.timedelta(days=9)
    horloge.t = t_acc + dt.timedelta(days=9) - dt.timedelta(minutes=1)
    assert tick(client_connecte).json()["envoyes"] == 0
    horloge.t = t_acc + dt.timedelta(days=9)
    assert tick(client_connecte).json()["envoyes"] == 1     # pas 4 : e-mail, acceptation + 9 j
    [mail] = lire_emails(fournisseurs_factices)
    assert mail["a"] == "prenom1@exemple.test" and "créneaux" in mail["texte"]
    assert _actions(fournisseurs_factices) == ["inviter", "ecrire", "ecrire"]
    assert _relire(session, insc).statut == "terminee"


def test_message_linkedin_pas_2_complet_et_signe(client_connecte):
    seqs = {s["cle"]: s for s in client_connecte.get("/sequences").json()}
    for s in seqs.values():
        for p in s["pas"]:
            assert "…" not in p["corps"] and "..." not in p["corps"]
    pas2 = seqs["entreprise-prospection"]["pas"][1]["corps"]
    assert "{prenom}" in pas2 and "vous" in pas2 and "€" not in pas2
    assert pas2.rstrip().endswith("Valentin, de MERCI")


def test_association_bienvenue_pas_1(client, session, horloge, fournisseurs_factices):
    from app.services import moteur_sequences
    org = creer_organisation(session, nom="Association Test 1", type="association", source="landing")
    c = creer_contact(session, type="association", email="asso@exemple.test", organisation_id=org.id)
    insc = moteur_sequences.inscrire(session, c, "association-bienvenue")
    session.commit()
    assert tick(client).json()["envoyes"] == 1
    [mail] = lire_emails(fournisseurs_factices)
    assert mail["a"] == "asso@exemple.test"
    assert mail["sujet"] == "Bienvenue dans le pilote, Association Test 1"
    assert "Association Test 1" in mail["texte"] and "sans frais" in mail["texte"]
    assert _relire(session, insc).statut == "terminee"
