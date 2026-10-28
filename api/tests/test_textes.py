"""Textes par défaut alignés sur le socle MERCI : portefeuille générosité pour les entreprises,
dons ponctuels pour les particuliers, pilote en Alsace."""
from __future__ import annotations

from pathlib import Path

from app.sequences import SEQUENCES

RACINE = Path(__file__).resolve().parents[2]


def _textes(cle: str | None = None) -> list[str]:
    seqs = [SEQUENCES[cle]] if cle else SEQUENCES.values()
    return [t for s in seqs for p in s.pas for t in (p.sujet, p.corps) if t]


def test_aucun_texte_ne_cite_strasbourg():
    assert all("Strasbourg" not in t for t in _textes())
    assert "Strasbourg" not in (RACINE / "web/app/(crm)/reglages/page.tsx").read_text()


def test_aucun_texte_ne_demande_lien_rdv():
    assert all("{lien_rdv}" not in t for t in _textes())


def test_aucun_tiret_long():
    assert all("\u2014" not in t and "\u2013" not in t for t in _textes())


def test_textes_entreprise_parlent_du_portefeuille_generosite():
    entrante = SEQUENCES["entreprise-entrante"].pas
    prospection = SEQUENCES["entreprise-prospection"].pas
    for p in (entrante[0], entrante[1], prospection[0], prospection[1], prospection[3]):
        assert "portefeuille générosité" in p.corps


def test_donateur_bienvenue_dons_ponctuels_sans_portefeuille():
    corps = SEQUENCES["donateur-bienvenue"].pas[0].corps
    assert "quand vous le souhaitez" in corps and "portefeuille" not in corps


def test_association_bienvenue_cite_les_salaries_des_entreprises():
    corps = SEQUENCES["association-bienvenue"].pas[0].corps
    assert "les dons des particuliers comme ceux des salariés des entreprises partenaires" in corps
