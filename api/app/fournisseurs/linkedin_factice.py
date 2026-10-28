"""LinkedInProvider local (section 6.3) : aucune personne trouvée par défaut, envois écrits dans
`outbox/linkedin.jsonl`. Les tests injectent des personnes, des profils et des erreurs."""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Literal, Mapping

from .. import temps
from ..config import settings
from .base import EvenementLinkedIn, PersonneLinkedIn, ProfilLinkedIn, SignatureInvalide

log = logging.getLogger("merci.linkedin")

TYPES = ("invitation_acceptee", "message_recu", "compte_deconnecte", "compte_ok")


class FauxLinkedInProvider:
    nom = "factice"

    def __init__(self, personnes: dict[str, list[PersonneLinkedIn]] | None = None,
                 profils: dict[str, ProfilLinkedIn] | None = None,
                 erreurs: dict[str, Exception] | None = None, dossier: str | Path | None = None):
        self.personnes = personnes or {}
        self.profils = profils or {}
        self.erreurs = erreurs or {}            # nom de méthode -> exception levée
        self.dossier = Path(dossier or settings.outbox_dir)
        self.appels: list[tuple] = []

    def _erreur(self, methode: str) -> None:
        if methode in self.erreurs:
            raise self.erreurs[methode]

    def etat_compte(self) -> Literal["ok", "a_reconnecter", "non_configure"]:
        return "ok"

    def chercher(self, entreprise: str, postes: list[str], limite: int) -> list[PersonneLinkedIn]:
        self.appels.append(("chercher", entreprise, list(postes), limite))
        self._erreur("chercher")
        return list(self.personnes.get(entreprise, []))

    def profil(self, provider_id: str) -> ProfilLinkedIn:
        self.appels.append(("profil", provider_id))
        self._erreur("profil")
        return self.profils.get(provider_id) or ProfilLinkedIn(
            provider_id=provider_id, prenom=None, nom=None, poste=None, entreprise=None, url=None)

    def _ecrire_outbox(self, action: str, provider_id: str, texte: str) -> str:
        ident = f"factice-{uuid.uuid4()}"
        self.dossier.mkdir(parents=True, exist_ok=True)
        ligne = {"id": ident, "action": action, "provider_id": provider_id, "texte": texte,
                 "at": temps.iso(temps.maintenant())}
        with (self.dossier / "linkedin.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        log.info("LinkedIn factice : %s écrit dans %s", action, self.dossier)
        return ident

    def inviter(self, provider_id: str, note: str) -> str:
        self.appels.append(("inviter", provider_id))
        self._erreur("inviter")
        return self._ecrire_outbox("inviter", provider_id, note)

    def ecrire(self, provider_id: str, texte: str) -> str:
        self.appels.append(("ecrire", provider_id))
        self._erreur("ecrire")
        return self._ecrire_outbox("ecrire", provider_id, texte)

    def verifier_acceptation(self, provider_id: str, url: str | None) -> None:
        return None  # l'acceptation arrive par le webhook normalisé

    def analyser_webhook(self, entetes: Mapping[str, str], corps: bytes) -> list[EvenementLinkedIn]:
        """JSON normalisé `{evenements: [{cle, type, provider_id, texte}]}`, en développement seulement."""
        if settings.mode != "development":
            raise SignatureInvalide("webhook non signé refusé")
        try:
            evenements = json.loads(corps)["evenements"]
            return [EvenementLinkedIn(cle=str(e["cle"]), type=e["type"] if e["type"] in TYPES else "autre",
                                      provider_id=e.get("provider_id"), texte=e.get("texte"),
                                      recu_at=temps.maintenant()) for e in evenements]
        except (ValueError, KeyError, TypeError) as exc:
            raise SignatureInvalide("corps illisible") from exc
