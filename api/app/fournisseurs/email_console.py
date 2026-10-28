"""EmailProvider local : écrit chaque message dans `outbox/` au lieu de l'envoyer."""
from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Mapping

from .. import temps
from ..config import settings
from .base import EvenementEmail, MessageEmail, SignatureInvalide
from .email_resend import lire_evenement

log = logging.getLogger("merci.email")

class ConsoleEmailProvider:
    nom = "console"

    def __init__(self, dossier: str | Path | None = None):
        self.dossier = Path(dossier or settings.outbox_dir)

    def envoyer(self, msg: MessageEmail) -> str:
        ident = f"console-{uuid.uuid4()}"
        cle = re.sub(r"[^\w-]", "-", msg.cle_idempotence or ident)[:60]
        base = f"{temps.maintenant():%Y%m%d-%H%M%S}_{cle}"
        self.dossier.mkdir(parents=True, exist_ok=True)
        contenu = {
            "id": ident, "a": msg.a, "sujet": msg.sujet, "expediteur": msg.expediteur,
            "repondre_a": msg.repondre_a, "entetes": msg.entetes, "etiquettes": msg.etiquettes,
            "texte": msg.texte,
        }
        (self.dossier / f"{base}.json").write_text(json.dumps(contenu, ensure_ascii=False, indent=2))
        (self.dossier / f"{base}.html").write_text(msg.html)
        log.info("e-mail écrit dans %s (%s)", self.dossier, base)
        return ident

    def analyser_webhook(self, entetes: Mapping[str, str], corps: bytes) -> list[EvenementEmail]:
        """JSON non signé au format Resend, accepté seulement en développement."""
        if settings.mode != "development":
            raise SignatureInvalide("webhook non signé refusé")
        return [lire_evenement(entetes.get("svix-id") or uuid.uuid4().hex, corps)]
