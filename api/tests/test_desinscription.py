"""Désinscription : lien et en-têtes des e-mails, page en un clic, RFC 8058 (section 4.10)."""
from __future__ import annotations

from sqlmodel import select

from app import securite
from app.modeles import Activite, Contact, InscriptionSequence
from conftest import donateur_inscrit, lire_emails, tick


def _url(contact_id: int) -> str:
    return f"/public/desinscription/{securite.jeton_desinscription(contact_id)}"


def test_email_contient_lien_et_entetes_list_unsubscribe(client, session, horloge, fournisseurs_factices):
    c, _ = donateur_inscrit(session)
    tick(client)
    [mail] = lire_emails(fournisseurs_factices)
    lien = f"http://127.0.0.1:8010{_url(c.id)}"
    assert mail["entetes"]["List-Unsubscribe"] == f"<{lien}>"
    assert mail["entetes"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert lien in mail["texte"]
    html = fournisseurs_factices.emails()[0].with_suffix(".html").read_text()
    assert lien in html and "Se désinscrire" in html
    assert "inscrit au pilote MERCI en Alsace" in html
    assert "Valentin, de MERCI" in html


def test_get_desinscrit_et_arrete_les_sequences(client, session, horloge):
    c, insc = donateur_inscrit(session)
    r = client.get(_url(c.id))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "C'est noté, vous ne recevrez plus nos e-mails." in r.text
    session.expire_all()
    assert session.get(Contact, c.id).desinscrit_at == horloge.t
    insc = session.get(InscriptionSequence, insc.id)
    assert (insc.statut, insc.raison_arret) == ("arretee", "desinscription")
    assert session.exec(select(Activite).where(Activite.type == "desinscription")).one().contact_id == c.id


def test_post_un_clic(client, session, horloge):
    c, _ = donateur_inscrit(session)
    r = client.post(_url(c.id), content=b"List-Unsubscribe=One-Click",
                    headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain") and r.text == "ok"
    session.expire_all()
    assert session.get(Contact, c.id).desinscrit_at is not None


def test_jeton_falsifie_400(client, session, horloge):
    c, _ = donateur_inscrit(session)
    jeton = securite.jeton_desinscription(c.id)
    for faux in (jeton[:-1] + ("A" if jeton[-1] != "A" else "B"), "n-importe-quoi", "MQ.abc"):
        r = client.get(f"/public/desinscription/{faux}")
        assert r.status_code == 400 and "Lien invalide" in r.text
    assert client.post("/public/desinscription/n-importe-quoi").status_code == 400
    session.expire_all()
    assert session.get(Contact, c.id).desinscrit_at is None


def test_desinscrit_ne_recoit_plus_rien(client, session, horloge, fournisseurs_factices):
    c, insc = donateur_inscrit(session)
    c.desinscrit_at = horloge.t  # posé hors de la route : l'inscription est encore active
    session.add(c)
    session.commit()
    assert tick(client).json()["envoyes"] == 0
    assert fournisseurs_factices.emails() == []


def test_desinscription_idempotente(client, session, horloge):
    c, _ = donateur_inscrit(session)
    t = horloge.t
    assert client.get(_url(c.id)).status_code == 200
    horloge.avancer(minutes=5)
    assert client.get(_url(c.id)).status_code == 200
    assert client.post(_url(c.id)).status_code == 200
    session.expire_all()
    assert session.get(Contact, c.id).desinscrit_at == t
    assert len(session.exec(select(Activite).where(Activite.type == "desinscription")).all()) == 1
