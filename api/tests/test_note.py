"""Note /10 MERCI : fonction pure, raisons lisibles (section 7.2)."""
from __future__ import annotations

import datetime as dt

from app.modeles import Organisation
from app.prospection import note

T = dt.datetime(2026, 10, 12, 8, 0)
POSTES = ["DRH", "RH", "RSE", "QVT", "People"]


def _org(tranche: str | None, signal_jours: int | None = None, libelle: str = "Post RSE") -> Organisation:
    return Organisation(
        type="entreprise", nom="Entreprise Test 1", source="prospection", tranche_effectif=tranche,
        signal_rse_at=None if signal_jours is None else T - dt.timedelta(days=signal_jours),
        signal_rse_libelle=None if signal_jours is None else libelle, cree_at=T, maj_at=T,
    )


def test_decideur_250_plus_signal_recent_10():
    n, raisons = note.calculer(_org("32", signal_jours=3), "Responsable RSE", POSTES, T)
    assert n == 10
    assert raisons == ["Décideur RSE trouvé +4", "250 salariés et plus +3", "Post RSE il y a 3 jours +3"]


def test_decideur_50_a_249_vaut_6():
    for tranche in ("21", "22", "31"):
        assert note.calculer(_org(tranche), "DRH", POSTES, T)[0] == 6


def test_decideur_moins_de_50_vaut_4():
    n, raisons = note.calculer(_org("12"), "DRH", POSTES, T)
    assert (n, raisons) == (4, ["Décideur DRH trouvé +4"])
    assert note.calculer(_org(None), "DRH", POSTES, T)[0] == 4


def test_sans_decideur_250_plus_vaut_3_et_raison_affichee():
    for tranche in ("32", "41", "42", "51", "52", "53"):
        n, raisons = note.calculer(_org(tranche), None, POSTES, T)
        assert (n, raisons) == (3, ["Aucun décideur RH ou RSE trouvé", "250 salariés et plus +3"])


def test_post_rse_de_30_jours_ne_compte_pas():
    assert note.calculer(_org("32", signal_jours=29), "DRH", POSTES, T)[0] == 10
    n, raisons = note.calculer(_org("32", signal_jours=30), "DRH", POSTES, T)
    assert n == 7 and not any("Post" in r for r in raisons)


def test_offre_qvt_compte_3():
    n, raisons = note.calculer(_org("21", signal_jours=10, libelle="Offre d'emploi QVT"), None, POSTES, T)
    assert n == 5
    assert raisons == ["Aucun décideur RH ou RSE trouvé", "50 à 249 salariés +2", "Offre d'emploi QVT ce mois +3"]


def test_libelles_des_raisons():
    # Libellé du décideur : premier poste de la cible présent dans l'intitulé (mot entier, sans accents).
    assert note.libelle_poste("DRH Groupe", POSTES) == "DRH"
    assert note.libelle_poste("Chargée RH et paie", POSTES) == "RH"
    assert note.libelle_poste("People & Culture Lead", POSTES) == "People"
    assert note.libelle_poste("Responsable qvt", POSTES) == "QVT"
    assert note.libelle_poste("Directeur commercial", POSTES) is None
    assert note.libelle_poste("THRONE consulting", POSTES) is None
    assert note.libelle_poste(None, POSTES) is None
    # Mots-clés RSE (décision D13), en minuscules sans accents.
    assert note.texte_rse("Notre démarche RSE avance")
    assert note.texte_rse("Responsabilité sociétale : nos engagements")
    assert note.texte_rse("Journée mécénat de compétences")
    assert note.texte_rse("Semaine de la QVCT")
    assert not note.texte_rse("Nouveau site internet")
    assert not note.texte_rse("Course de vitesse")  # « rse » seulement en mot entier
    # Singulier pour un jour.
    assert note.calculer(_org("32", signal_jours=1), "DRH", POSTES, T)[1][2] == "Post RSE il y a 1 jour +3"
