"""Choix des fournisseurs selon l'environnement (section 6.2).

Les fabriques sont des dépendances FastAPI : les tests les remplacent par `dependency_overrides`.
"""
from __future__ import annotations

from ..config import settings
from .base import CrmExterneProvider, EmailProvider, LinkedInProvider, NonConfigure


def get_email_provider() -> EmailProvider:
    if settings.resend_api_key:
        from .email_resend import ResendEmailProvider
        return ResendEmailProvider(settings.resend_api_key, settings.resend_webhook_secret)
    if settings.mode == "production" and settings.exiger_fournisseurs:
        raise NonConfigure("Boîte locale refusée en production : RESEND_API_KEY requis")
    from .email_console import ConsoleEmailProvider
    return ConsoleEmailProvider()


def get_linkedin_provider() -> LinkedInProvider:
    """`LINKEDIN_FOURNISSEUR` : factice (défaut, refusé en production) ou connectsafely."""
    choix = settings.linkedin_fournisseur
    if choix == "connectsafely":
        if not (settings.connectsafely_api_key and settings.connectsafely_account_id):
            raise NonConfigure("ConnectSafely : CONNECTSAFELY_API_KEY et CONNECTSAFELY_ACCOUNT_ID requis")
        from .linkedin_connectsafely import ConnectSafelyLinkedInProvider
        return ConnectSafelyLinkedInProvider(settings.connectsafely_api_key, settings.connectsafely_account_id,
                                             settings.linkedin_webhook_secret)
    if settings.mode == "production" and settings.exiger_fournisseurs:
        raise NonConfigure("LinkedIn factice refusé en production : LINKEDIN_FOURNISSEUR requis")
    from .linkedin_factice import FauxLinkedInProvider
    return FauxLinkedInProvider()


def get_crm_externe_provider() -> CrmExterneProvider:
    """`HUBSPOT_TOKEN` renseigné : HubSpot ; vide : factice (journalise, n'appelle rien).
    Accepté en production : le CRM MERCI fonctionne sans HubSpot, l'écran Réglages l'indique."""
    if settings.hubspot_token:
        from .crm_hubspot import HubspotCrmProvider
        return HubspotCrmProvider(settings.hubspot_token)
    from .crm_factice import FauxCrmProvider
    return FauxCrmProvider()
