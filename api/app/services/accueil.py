"""Accueil et coque : compteurs du parcours, liste « à faire », relances, arrivés par la landing
(section 4.4). Tout est dérivé de l'état, rien n'est stocké (décision D7)."""
from __future__ import annotations

from collections import Counter

import sqlalchemy as sa
from sqlmodel import Session, select

from .. import temps
from ..config import settings
from ..modeles import Activite, InscriptionSequence, Reglage
from ..pipelines import ETAPES_PARCOURS, PIPELINES, RATTACHE, cles_etapes, etape, etape_perdue
from . import contacts as svc_contacts
from . import moteur_sequences

A_FAIRE_ETAPES = {
    ("entreprises", "demo_planifiee"): ("demo_a_preparer", "Préparer la démo", "calendrier"),
    ("entreprises", "demo_faite"): ("signature", "Relancer pour la signature", "coche"),
    ("entreprises", "abonnement_signe"): ("activer_salaries", "Envoyer le lien d'invitation des salariés", "coche"),
    ("associations", "inscrite"): ("appeler_association", "Appeler l'association", "telephone"),
}


def etat_linkedin(reglage: Reglage) -> str:
    """Fournisseur factice jamais vérifié : « non configuré » (aucune clé LinkedIn)."""
    if settings.linkedin_fournisseur == "factice" and reglage.linkedin_etat == "inconnu":
        return "non_configure"
    return reglage.linkedin_etat


def creneau(reglage: Reglage) -> dict:
    return {"jours": [int(j) for j in reglage.creneau_jours.split(",") if j.strip()],
            "debut": reglage.creneau_debut, "fin": reglage.creneau_fin}


def coque(session: Session) -> dict:
    r = session.get(Reglage, 1)

    def compter(statut: str) -> int:
        return int(session.exec(select(sa.func.count()).select_from(InscriptionSequence).where(
            InscriptionSequence.statut == statut)).one())

    return {
        "aujourdhui": temps.jour_paris(temps.maintenant()).isoformat(),
        "nb_contacts": svc_contacts.nb_lignes(session),
        "nb_sequences_en_cours": compter("active"),
        "relances_en_pause": r.relances_en_pause,
        "creneau": creneau(r),
        "linkedin": {"fournisseur": settings.linkedin_fournisseur, "etat": etat_linkedin(r)},
        "nb_echecs": compter("echec"),
    }


def _detail(compteur: Counter, ordre: list[str] | None = None) -> list[dict]:
    rang = {libelle: i for i, libelle in enumerate(ordre or [])}
    tries = sorted(compteur.items(), key=lambda kv: (-kv[1], rang.get(kv[0], len(rang)), kv[0]))
    return [{"libelle": libelle, "n": n} for libelle, n in tries]


def _parcours(vue: svc_contacts.Vue) -> dict:
    publics = []
    for pipeline in ("donateurs", "entreprises"):
        perdue = etape_perdue(pipeline)
        noms = [etape(pipeline, c)["nom"] for c in cles_etapes(pipeline)]
        n = Counter()
        details: dict[str, Counter] = {e["cle"]: Counter() for e in ETAPES_PARCOURS}
        for a in vue.affaires:
            if a.pipeline != pipeline or a.etape == perdue:
                continue
            contact = vue.contacts.get(a.contact_id) if a.contact_id else None
            if pipeline == "donateurs":
                origine = svc_contacts.libelle_detail((contact.source_detail if contact else None) or
                                                      svc_contacts.SOURCES_LIBELLES[contact.source if contact else "manuel"])
            else:
                org = vue.orgs.get(a.organisation_id) if a.organisation_id else None
                source = contact.source if contact else (org.source if org else "manuel")
                origine = svc_contacts.SOURCES_LIBELLES[source]
            n["attirer"] += 1
            details["attirer"][origine] += 1
            case = RATTACHE[pipeline].get(a.etape)
            if case:
                n[case] += 1
                details[case][etape(pipeline, a.etape)["nom"]] += 1
        publics.append({
            "pipeline": pipeline, "nom": PIPELINES[pipeline]["nom"],
            "cases": {e["cle"]: {"n": n[e["cle"]], "detail": _detail(details[e["cle"]], noms)}
                      for e in ETAPES_PARCOURS},
        })
    return {"etapes": ETAPES_PARCOURS, "publics": publics}


def _reponses_non_traitees(session: Session) -> dict[int, Activite]:
    """Dernière réponse LinkedIn de chaque contact, si l'équipe n'a rien noté depuis."""
    reponses: dict[int, Activite] = {}
    equipe: dict[int, int] = {}
    for a in session.exec(select(Activite).where(
            Activite.contact_id.is_not(None),
            Activite.type.in_(("linkedin_reponse", "note", "appel"))).order_by(Activite.id)):
        if a.type == "linkedin_reponse":
            reponses[a.contact_id] = a
        else:
            equipe[a.contact_id] = a.id
    return {cid: a for cid, a in reponses.items() if equipe.get(cid, 0) < a.id}


def _a_faire(session: Session, vue: svc_contacts.Vue) -> list[dict]:
    reponses = _reponses_non_traitees(session)
    items: list[tuple[int, object, dict]] = []

    def item(rang, depuis, type, titre, sous_titre, cible, pastille, ton=None, bouton="Ouvrir"):
        items.append((rang, depuis, {"type": type, "titre": titre, "sous_titre": sous_titre, "cible": cible,
                                     "pastille": pastille, "ton": ton, "bouton": bouton,
                                     "depuis": temps.iso(depuis)}))

    for a in vue.affaires:
        contact = vue.contacts.get(a.contact_id) if a.contact_id else None
        org = vue.orgs.get(a.organisation_id) if a.organisation_id else None
        if org is None and contact is not None and contact.organisation_id:
            org = vue.orgs.get(contact.organisation_id)
        cible = {"genre": "contact", "id": contact.id} if contact else {"genre": "organisation", "id": org.id}
        qui = ", ".join(x for x in (svc_contacts.nom_affiche(contact, org) if contact else None,
                                    org.nom if org else None) if x)
        if a.pipeline == "entreprises" and a.etape == "a_repondu":
            reponse = reponses.get(contact.id) if contact else None
            if reponse:
                lieu = ", ".join(x for x in (contact.poste, org.nom if org else None) if x)
                item(0, reponse.cree_at, "reponse", f"{contact.prenom or svc_contacts.nom_affiche(contact, org)} "
                     "a répondu sur LinkedIn", f"{lieu}. Planifier la démo." if lieu else "Planifier la démo.",
                     cible, "linkedin", "vert", "Lire la réponse")
            else:
                item(2, a.etape_depuis, "demo_a_planifier", "Planifier la démo", qui, cible, "coche")
        elif (a.pipeline, a.etape) in A_FAIRE_ETAPES:
            type, titre, pastille = A_FAIRE_ETAPES[(a.pipeline, a.etape)]
            item(2, a.etape_depuis, type, titre, qui, cible, pastille)

    for liste in vue.inscriptions.values():
        for insc in liste:
            if insc.statut != "echec":
                continue
            contact = vue.contacts[insc.contact_id]
            nom = svc_contacts.nom_affiche(contact, vue.orgs.get(contact.organisation_id))
            titre = f"E-mail en rebond pour {nom}" if insc.raison_arret == "rebond" else f"Envoi en échec pour {nom}"
            sous = f"{contact.email}. La séquence est suspendue." if contact.email else "La séquence est suspendue."
            item(1, insc.maj_at, "echec", titre, sous, {"genre": "contact", "id": contact.id},
                 "attention", "poudre", "Corriger")

    items.sort(key=lambda x: (x[0], x[1]))
    return [x[2] for x in items]


def _relances(vue: svc_contacts.Vue) -> dict:
    n = Counter()
    for liste in vue.inscriptions.values():
        for insc in liste:
            n[moteur_sequences.etat(insc, vue.contacts[insc.contact_id], vue.ctx)["etat"]] += 1
    return {"partent_aujourdhui": n["due"], "en_cours": n["active"], "en_pause": n["pause"], "en_echec": n["echec"]}


def _arrives_landing(vue: svc_contacts.Vue) -> list[dict]:
    recents = sorted((c for c in vue.contacts.values() if c.source == "landing"),
                     key=lambda c: (c.cree_at, c.id), reverse=True)[:4]
    resultat = []
    for c in recents:
        org = vue.orgs.get(c.organisation_id) if c.organisation_id else None
        resultat.append({"cible": {"genre": "contact", "id": c.id}, "nom_affiche": svc_contacts.nom_affiche(c, org),
                         "type": c.type, "organisation_nom": org.nom if org else None,
                         "source_detail": c.source_detail, "cree_at": temps.iso(c.cree_at)})
    return resultat


def accueil(session: Session) -> dict:
    vue = svc_contacts.Vue(session)
    return {
        "parcours": _parcours(vue),
        "a_faire": _a_faire(session, vue),
        "relances": _relances(vue),
        "arrives_landing": _arrives_landing(vue),
    }
