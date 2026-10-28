"""Accueil (section 4.4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from ..auth import membre_connecte
from ..db import get_session
from ..services import accueil as svc

router = APIRouter(tags=["accueil"], dependencies=[Depends(membre_connecte)])


@router.get("/accueil")
def accueil(session: Session = Depends(get_session)):
    return svc.accueil(session)
