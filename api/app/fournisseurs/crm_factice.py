"""CrmExterneProvider factice (sans `HUBSPOT_TOKEN`) : journalise ce qui serait envoyé, n'appelle rien.

`connecte` est faux : la synchro n'écrit aucun identifiant et laisse les objets « à synchroniser »,
pour qu'ils partent vraiment dès qu'un jeton est renseigné.
"""
from __future__ import annotations

import json
import logging

from .base import ProprieteCrm

log = logging.getLogger("merci.hubspot")


class FauxCrmProvider:
    nom = "factice"
    connecte = False

    def __init__(self):
        self._n = 0

    def _journal(self, action: str, **donnees) -> None:
        log.info("HubSpot factice, %s : %s", action, json.dumps(donnees, ensure_ascii=False, sort_keys=True))

    def _id(self, objet: str) -> str:
        self._n += 1
        return f"factice-{objet}-{self._n}"

    def assurer_proprietes(self, groupe: tuple[str, str], proprietes: list[ProprieteCrm]) -> None:
        self._journal("propriétés", groupe=groupe[0], noms=sorted({p.nom for p in proprietes}))

    def upsert_contact(self, email: str, proprietes: dict[str, str]) -> str:
        self._journal("upsert contact", email=email, proprietes=proprietes)
        return self._id("contacts")

    def creer(self, objet: str, proprietes: dict[str, str]) -> str:
        self._journal(f"création {objet}", proprietes=proprietes)
        return self._id(objet)

    def modifier(self, objet: str, ident: str, proprietes: dict[str, str]) -> None:
        self._journal(f"mise à jour {objet}", id=ident, proprietes=proprietes)

    def associer(self, objet: str, ident: str, vers: str, vers_ident: str | None) -> None:
        self._journal("association", de=f"{objet}/{ident}", vers=f"{vers}/{vers_ident}")

    def etapes_pipeline(self) -> list[dict[str, str]]:
        return []
