"""Lien de connexion au CRM sans e-mail, tant que Resend n'est pas branché.

Usage, depuis `api/` :
    DATABASE_URL=<url de la base> WEB_URL=https://<crm> MODE=development \
        .venv/bin/python -m scripts.lien_connexion [adresse]

Crée un jeton à usage unique (15 minutes) pour un membre actif, comme `POST /auth/lien`,
et affiche le lien au lieu de l'envoyer. Adresse par défaut : ADMIN_EMAIL.
"""
from __future__ import annotations

import sys

from sqlmodel import Session, select

from app import auth, db, temps
from app.config import settings
from app.modeles import JetonConnexion, Membre, normaliser_email


def main() -> int:
    email = normaliser_email(sys.argv[1] if len(sys.argv) > 1 else settings.admin_email)
    with Session(db.engine) as session:
        membre = session.exec(select(Membre).where(Membre.email == email)).first()
        if membre is None or not membre.actif:
            print(f"Aucun membre actif pour {email}", file=sys.stderr)
            return 1
        jeton = auth.new_magic_token()
        t = temps.maintenant()
        session.add(JetonConnexion(jeton_hash=auth.hash_magic_token(jeton), email=membre.email,
                                   expire_at=t + auth.DUREE_LIEN, cree_at=t))
        session.commit()
    print(f"{settings.web_url.rstrip('/')}/connexion/verifier?jeton={jeton}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
