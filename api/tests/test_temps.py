from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from app import temps

SEMAINE = SimpleNamespace(creneau_jours="1,2,3,4,5", creneau_debut=9, creneau_fin=18)


def test_maintenant_utc_naif():
    t = temps.maintenant()
    assert t.tzinfo is None
    assert abs((dt.datetime.now(dt.timezone.utc).replace(tzinfo=None) - t).total_seconds()) < 5


def test_vers_paris_heure_ete_et_hiver():
    assert temps.vers_paris(dt.datetime(2026, 7, 1, 7, 0)).hour == 9   # UTC+2
    assert temps.vers_paris(dt.datetime(2026, 12, 1, 8, 0)).hour == 9  # UTC+1


def test_dans_creneau_bornes():
    # lundi 12/10/2026 : 9 h Paris = 7 h UTC (heure d'été)
    assert not temps.dans_creneau(dt.datetime(2026, 10, 12, 6, 59), SEMAINE)
    assert temps.dans_creneau(dt.datetime(2026, 10, 12, 7, 0), SEMAINE)
    assert temps.dans_creneau(dt.datetime(2026, 10, 12, 15, 59), SEMAINE)
    assert not temps.dans_creneau(dt.datetime(2026, 10, 12, 16, 0), SEMAINE)
    # samedi 17/10/2026, 12 h Paris
    assert not temps.dans_creneau(dt.datetime(2026, 10, 17, 10, 0), SEMAINE)
