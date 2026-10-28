"""Fixtures pytest du CRM MERCI.

Les variables d'environnement sont posées avant tout import de `app` (settings lu à l'import).
Aucun appel réseau : le transport HTTP réel de httpx est remplacé par une fonction qui lève
une erreur ; seuls les `httpx.MockTransport` injectés fonctionnent.
Base : un modèle migré une fois par `alembic upgrade head`, copié pour chaque test.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import sys
import tempfile
from pathlib import Path

API = Path(__file__).resolve().parent.parent
_TMP = Path(tempfile.mkdtemp(prefix="merci-tests-"))
_MODELE = _TMP / "modele.db"

os.environ["MODE"] = "development"
os.environ["DATABASE_URL"] = f"sqlite:///{_MODELE}"
os.environ["OUTBOX_DIR"] = str(_TMP / "outbox")
os.environ["ADMIN_EMAIL"] = "Admin@Exemple.test"
os.environ["ADMIN_PRENOM"] = "Admin Test"
os.environ["HUBSPOT_TOKEN"] = ""  # HubSpot factice, quel que soit le .env local
os.chdir(API)
sys.path.insert(0, str(API))

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, create_engine, select  # noqa: E402

from app import db as db_mod, fournisseurs, securite, temps  # noqa: E402
from app.auth import COOKIE_SESSION, create_jwt  # noqa: E402
from app.config import settings  # noqa: E402
from app.fournisseurs.email_console import ConsoleEmailProvider  # noqa: E402
from app.fournisseurs.linkedin_factice import FauxLinkedInProvider  # noqa: E402
from app.main import app  # noqa: E402
from app.modeles import Membre  # noqa: E402


class ReseauInterdit(RuntimeError):
    """Levée par tout appel réseau réel pendant les tests."""


def _reseau_interdit(self, request):
    raise ReseauInterdit(f"appel réseau interdit pendant les tests : {request.method} {request.url}")


def alembic_config() -> Config:
    return Config(str(API / "alembic.ini"))


command.upgrade(alembic_config(), "head")  # base modèle, migrée une seule fois


@pytest.fixture(autouse=True)
def _blocage_reseau(monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _reseau_interdit)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _reseau_interdit)
    yield


@pytest.fixture(autouse=True)
def _limites_remises_a_zero():
    securite.reinitialiser_limites()
    yield


class Horloge:
    """Horloge figée et avançable (UTC naïf). Défaut : lundi 12/10/2026, 10 h à Paris."""

    def __init__(self, t: dt.datetime):
        self.t = t

    def __call__(self) -> dt.datetime:
        return self.t

    def avancer(self, **delta) -> dt.datetime:
        self.t += dt.timedelta(**delta)
        return self.t


@pytest.fixture()
def horloge(monkeypatch):
    h = Horloge(dt.datetime(2026, 10, 12, 8, 0, 0))
    monkeypatch.setattr(temps, "maintenant", h)
    return h


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    chemin = tmp_path / "test.db"
    shutil.copy(_MODELE, chemin)
    url = f"sqlite:///{chemin}"
    eng = create_engine(url, connect_args={"check_same_thread": False})
    monkeypatch.setattr(settings, "database_url", url)
    monkeypatch.setattr(db_mod, "engine", eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


class Fournisseurs:
    def __init__(self, outbox: Path):
        self.outbox = outbox
        self.email = ConsoleEmailProvider(dossier=outbox)
        self.linkedin = FauxLinkedInProvider(dossier=outbox)

    def emails(self) -> list[Path]:
        return sorted(self.outbox.glob("*.json")) if self.outbox.exists() else []

    def linkedin_envois(self) -> list[dict]:
        import json
        fichier = self.outbox / "linkedin.jsonl"
        if not fichier.exists():
            return []
        return [json.loads(ligne) for ligne in fichier.read_text().splitlines() if ligne.strip()]


@pytest.fixture()
def fournisseurs_factices(tmp_path):
    return Fournisseurs(tmp_path / "outbox")


@pytest.fixture()
def client(engine, fournisseurs_factices):
    def _get_session():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[db_mod.get_session] = _get_session
    app.dependency_overrides[fournisseurs.get_email_provider] = lambda: fournisseurs_factices.email
    app.dependency_overrides[fournisseurs.get_linkedin_provider] = lambda: fournisseurs_factices.linkedin
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def creer_membre(session: Session, email: str, prenom: str = "Prénom Test",
                 role: str = "equipe", actif: bool = True) -> Membre:
    m = Membre(email=email, prenom=prenom, role=role, actif=actif, cree_at=temps.maintenant())
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def connecter(client: TestClient, membre: Membre) -> TestClient:
    client.cookies.set(COOKIE_SESSION, create_jwt(membre.id, membre.email))
    return client


@pytest.fixture()
def admin(client, session) -> Membre:
    """L'admin créé au démarrage depuis ADMIN_EMAIL."""
    return session.exec(select(Membre).where(Membre.email == "admin@exemple.test")).one()


@pytest.fixture()
def membre(client, session) -> Membre:
    return creer_membre(session, "prenom@exemple.test")


@pytest.fixture()
def client_connecte(client, admin) -> TestClient:
    return connecter(client, admin)


# ---------------------------------------------------------------------------
# Aides des lots suivants : données de test visiblement fictives, formes du contrat.

from app.modeles import Affaire, Contact, InscriptionSequence, Organisation  # noqa: E402

TEXTE_CONSENTEMENT = "J'accepte que MERCI m'écrive au sujet du pilote."


def corps_inscription(profil: str = "donateur", **kw) -> dict:
    corps = {
        "profil": profil,
        "prenom": "Prénom Test",
        "email": "prenom@exemple.test",
        "structure": "" if profil == "donateur" else "Entreprise Test 1",
        "source": "landing-v1-galet",
        "date": "2026-10-12T07:59:00.000Z",
        "consentement": True,
        "consentement_texte": TEXTE_CONSENTEMENT,
    }
    corps.update(kw)
    return corps


def inscrire_landing(client: TestClient, profil: str = "donateur", **kw):
    return client.post("/public/inscription", json=corps_inscription(profil, **kw))


def creer_contact(session: Session, *, type: str = "donateur", prenom: str | None = "Prénom Test",
                  nom: str | None = None, email: str | None = None, source: str = "landing",
                  **champs) -> Contact:
    t = temps.maintenant()
    c = Contact(type=type, prenom=prenom, nom=nom, email=email, source=source,
                cree_at=t, maj_at=t, **champs)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def creer_organisation(session: Session, nom: str = "Entreprise Test 1", *, type: str = "entreprise",
                       source: str = "prospection", **champs) -> Organisation:
    t = temps.maintenant()
    o = Organisation(type=type, nom=nom, source=source, cree_at=t, maj_at=t, **champs)
    session.add(o)
    session.commit()
    session.refresh(o)
    return o


def creer_affaire(session: Session, pipeline: str, etape: str, *, contact_id: int | None = None,
                  organisation_id: int | None = None) -> Affaire:
    t = temps.maintenant()
    a = Affaire(pipeline=pipeline, etape=etape, etape_depuis=t, contact_id=contact_id,
                organisation_id=organisation_id, cree_at=t, maj_at=t)
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


def creer_inscription(session: Session, contact_id: int, sequence: str, *, statut: str = "active",
                      pas_courant: int = 1, prochain_envoi_at: dt.datetime | None = None,
                      raison_arret: str | None = None) -> InscriptionSequence:
    t = temps.maintenant()
    i = InscriptionSequence(contact_id=contact_id, sequence=sequence, pas_courant=pas_courant,
                            prochain_envoi_at=prochain_envoi_at, ancre_at=t, statut=statut,
                            raison_arret=raison_arret, cree_at=t, maj_at=t)
    session.add(i)
    session.commit()
    session.refresh(i)
    return i


# Clés exactes des types partagés (section 4.2).
CLES_MEMBRE = {"id", "email", "prenom", "role", "actif"}
CLES_ETAPE = {"cle", "nom"}
CLES_ETAT_SEQUENCE = {"inscription_id", "sequence", "nom", "pas", "total", "etat",
                      "prochain_envoi_at", "attente", "raison"}
CLES_ORGANISATION = {"id", "type", "nom", "siren", "ville", "code_postal", "departement",
                     "tranche_effectif", "effectif_libelle", "naf_code", "naf_libelle", "site_web",
                     "note", "raisons"}
CLES_CONTACT = {"id", "type", "prenom", "nom", "email", "telephone", "poste", "ville", "linkedin_url",
                "source", "source_detail", "consentement_at", "consentement_texte", "desinscrit_at",
                "pause", "cree_at"}
CLES_AFFAIRE = {"id", "pipeline", "etape", "etape_depuis", "etapes_possibles", "responsable",
                "montant_mensuel", "perdue_raison"}
CLES_ACTIVITE = {"id", "type", "canal", "titre", "texte", "fort", "auteur", "cree_at"}
CLES_PASDEF = {"numero", "canal", "delai_libelle", "titre", "sujet", "corps", "personnalise"}
CLES_SEQUENCEDEF = {"cle", "nom", "public", "declencheur", "coupee", "pas"}
CLES_FICHE = {"genre", "id", "contact", "organisation", "affaire", "autres_contacts", "sequence",
              "sequences_possibles", "activites", "activites_suivant", "hubspot"}
CLES_LIGNE = {"genre", "id", "nom_affiche", "sous_titre", "type", "email", "organisation", "ville",
              "source", "source_detail", "affaire", "note", "sequence", "derniere_activite"}
CLES_CARTE = {"affaire_id", "cible", "titre", "sous_titre", "note", "sequence"}


def iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Aides du lot L4 : tick, inscriptions prêtes à partir, fournisseur e-mail remplaçable.

def tick(client: TestClient, secret: str | None = None):
    return client.post("/cron/tick", headers={"X-Cron-Secret": secret or settings.cron_secret})


def utiliser_email(fournisseur) -> None:
    """Remplace le fournisseur e-mail de l'application (tick, capture, webhooks)."""
    app.dependency_overrides[fournisseurs.get_email_provider] = lambda: fournisseur


def donateur_inscrit(session: Session, email: str = "prenom@exemple.test", etape: str = "inscrit",
                     sequence: str = "donateur-bienvenue", **champs):
    """Contact donateur, affaire, inscription active due maintenant. Renvoie (contact, inscription)."""
    from app.services import moteur_sequences
    c = creer_contact(session, email=email, **champs)
    creer_affaire(session, "donateurs", etape, contact_id=c.id)
    insc = moteur_sequences.inscrire(session, c, sequence)
    session.commit()
    session.refresh(insc)
    return c, insc


def entreprise_inscrite(session: Session, email: str | None = "prenom@exemple.test",
                        sequence: str = "entreprise-entrante", etape: str = "prospect", **champs):
    from app.services import moteur_sequences
    org = creer_organisation(session, source="landing")
    c = creer_contact(session, type="entreprise", email=email, organisation_id=org.id, **champs)
    creer_affaire(session, "entreprises", etape, contact_id=c.id, organisation_id=org.id)
    insc = moteur_sequences.inscrire(session, c, sequence)
    session.commit()
    session.refresh(insc)
    return c, insc


def regler(session: Session, **valeurs) -> None:
    from app.modeles import Reglage
    r = session.get(Reglage, 1)
    for k, v in valeurs.items():
        setattr(r, k, v)
    session.add(r)
    session.commit()


def lire_emails(f: "Fournisseurs") -> list[dict]:
    import json
    return [json.loads(p.read_text()) for p in f.emails()]


# ---------------------------------------------------------------------------
# Aides du lot L5 : LinkedIn factice remplaçable, prospect inscrit à la prospection.

def utiliser_linkedin(fournisseur) -> None:
    """Remplace le fournisseur LinkedIn de l'application (tick, prospection, webhooks)."""
    app.dependency_overrides[fournisseurs.get_linkedin_provider] = lambda: fournisseur


def prospect_inscrit(session: Session, n: int = 1, email: str | None = None):
    """Décideur trouvé par la prospection, inscrit à `entreprise-prospection`, dû maintenant.
    Renvoie (contact, inscription)."""
    from app.services import moteur_sequences
    org = creer_organisation(session, f"Entreprise Test {n}", siren=f"{n:09d}", tranche_effectif="32")
    c = creer_contact(session, type="entreprise", prenom=f"Prénom{n}", nom="Test", email=email,
                      source="prospection", poste="DRH", organisation_id=org.id,
                      linkedin_provider_id=f"factice-personne-{n}")
    creer_affaire(session, "entreprises", "prospect", contact_id=c.id, organisation_id=org.id)
    insc = moteur_sequences.inscrire(session, c, "entreprise-prospection")
    session.commit()
    session.refresh(insc)
    return c, insc


@pytest.fixture()
def sans_envoi_immediat(monkeypatch):
    """Pour les tests de listes et de fiches : l'état juste après la capture, avant tout envoi."""
    from app.services import capture
    monkeypatch.setattr(capture, "executer_inscriptions", lambda ids, fournisseur: None)
