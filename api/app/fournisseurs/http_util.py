"""Utilitaires HTTP partagés par les fournisseurs."""
from __future__ import annotations

from typing import Mapping


def entete(entetes: Mapping[str, str], nom: str) -> str | None:
    """Lecture d'un en-tête insensible à la casse."""
    return next((v for k, v in entetes.items() if k.lower() == nom.lower()), None)
