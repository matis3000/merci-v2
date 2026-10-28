"""Mise en page des e-mails MERCI (HTML + texte brut).

Porté au lot L1, branché aux lots L2 et L4. Mise en page « email-safe » : tableaux, styles
en ligne, préen-tête caché, carte blanche, logo par URL publique (jamais d'image `data:`,
bloquée par les messageries). DA MERCI : fond crème, Figtree avec repli Arial, texte encre,
bouton plat vert à texte noir, rayon 8 px, aucun montant.
"""
from __future__ import annotations

import html
import re

from ..config import settings

FONT = "Figtree,Arial,sans-serif"
ENCRE, ENCRE_2, FILET, CREME, VERT = "#000000", "#45433E", "#E4DFD3", "#F1EDE3", "#53C973"
RAISON = "Vous recevez ce message car vous vous êtes inscrit au pilote MERCI en Alsace."


def logo_url() -> str:
    return f"{settings.web_url.rstrip('/')}/assets/logo-noir.png"


def mise_en_page(preentete: str, interieur: str, lien_desinscription: str | None = None) -> str:
    """Gabarit commun : fond crème, logo, carte blanche, pied (expéditeur, raison, désinscription)."""
    pied = html.escape(settings.email_expediteur_nom)
    if lien_desinscription:
        lien = html.escape(lien_desinscription, quote=True)
        pied += (f"<br>{html.escape(RAISON)}<br>"
                 f'<a href="{lien}" style="color:{ENCRE_2};text-decoration:underline;">Se désinscrire</a>')
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light only">
<title>MERCI</title></head>
<body style="margin:0;padding:0;background:{CREME};-webkit-text-size-adjust:100%;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent;">{html.escape(preentete)}&#8204;&nbsp;&#8204;&nbsp;&#8204;&nbsp;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{CREME};">
  <tr><td align="center" style="padding:40px 16px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:480px;">
      <tr><td style="padding:0 4px 20px;">
        <img src="{html.escape(logo_url(), quote=True)}" width="96" alt="MERCI" style="display:block;border:0;width:96px;height:auto;">
      </td></tr>
      <tr><td style="background:#ffffff;border:1px solid {FILET};border-radius:8px;padding:32px 28px;font-family:{FONT};color:{ENCRE};">
        {interieur}
      </td></tr>
      <tr><td style="padding:20px 4px 0;font-family:{FONT};font-size:12px;line-height:18px;color:{ENCRE_2};">
        {pied}
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""


def titre(texte: str) -> str:
    return f'<h1 style="margin:0 0 12px;font-size:22px;line-height:28px;font-weight:700;color:{ENCRE};">{html.escape(texte)}</h1>'


def paragraphe(texte: str, taille: int = 15, couleur: str = ENCRE, marge: str = "0 0 20px") -> str:
    """`texte` est échappé : les variables d'un contact ne peuvent pas injecter de HTML."""
    return (f'<p style="margin:{marge};font-size:{taille}px;line-height:{taille + 9}px;color:{couleur};">'
            f"{html.escape(texte)}</p>")


def bouton(libelle: str, url: str) -> str:
    u = html.escape(url, quote=True)
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0">
          <tr><td align="center" bgcolor="{VERT}" style="border-radius:8px;">
            <a href="{u}" style="display:inline-block;padding:13px 24px;font-family:{FONT};font-size:15px;font-weight:600;color:{ENCRE};text-decoration:none;border-radius:8px;">{html.escape(libelle)}</a>
          </td></tr></table>"""


def filet() -> str:
    return f'<hr style="border:0;border-top:1px solid {FILET};margin:20px 0;">'


def lien_magique(url: str) -> tuple[str, str, str]:
    """(sujet, html, texte) du lien de connexion de l'équipe (valable 15 minutes, usage unique)."""
    sujet = "Votre lien de connexion au CRM MERCI"
    interieur = (
        titre("Connexion au CRM MERCI")
        + paragraphe("Cliquez sur le bouton pour ouvrir le CRM. Aucun mot de passe n'est nécessaire.", couleur=ENCRE_2)
        + bouton("Ouvrir le CRM", url)
        + paragraphe("Lien valable 15 minutes, à usage unique.", taille=14, couleur=ENCRE_2, marge="20px 0 0")
        + filet()
        + paragraphe("Le bouton ne fonctionne pas ? Copiez ce lien dans votre navigateur :",
                     taille=13, couleur=ENCRE_2, marge="0 0 6px")
        + f'<p style="margin:0;font-size:12px;line-height:18px;word-break:break-all;">'
          f'<a href="{html.escape(url, quote=True)}" style="color:{ENCRE_2};">{html.escape(url)}</a></p>'
    )
    texte = (
        "Bonjour,\n\n"
        f"Cliquez pour ouvrir le CRM MERCI :\n{url}\n\n"
        "Lien valable 15 minutes, à usage unique.\n\n"
        f"{settings.email_expediteur_nom}"
    )
    return sujet, mise_en_page("Votre lien de connexion (valable 15 minutes)", interieur), texte


def notification_association(structure: str, prenom: str, email: str, url_fiche: str) -> tuple[str, str, str]:
    """(sujet, html, texte) du message de service envoyé à l'équipe quand une association s'inscrit."""
    sujet = f"Nouvelle association inscrite : {structure}"
    interieur = (
        titre("Nouvelle association inscrite")
        + paragraphe(f"{structure} vient de s'inscrire sur la landing.")
        + paragraphe(f"Contact : {prenom}, {email}", couleur=ENCRE_2)
        + bouton("Ouvrir la fiche", url_fiche)
    )
    texte = (
        f"{structure} vient de s'inscrire sur la landing.\n\n"
        f"Contact : {prenom}, {email}\n\n"
        f"Ouvrir la fiche : {url_fiche}\n\n"
        f"{settings.email_expediteur_nom}"
    )
    return sujet, mise_en_page(f"{structure} vient de s'inscrire", interieur), texte


_URL = re.compile(r"https?://[^\s<]+")


def _paragraphe_avec_liens(texte: str) -> str:
    """Paragraphe d'un texte de séquence : échappé, retours à la ligne gardés, adresses web cliquables."""
    echappe = html.escape(texte)
    avec_liens = _URL.sub(lambda m: f'<a href="{m.group(0)}" style="color:{ENCRE};text-decoration:underline;">'
                                    f"{m.group(0)}</a>", echappe)
    return (f'<p style="margin:0 0 16px;font-size:15px;line-height:24px;color:{ENCRE};">'
            f"{avec_liens.replace(chr(10), '<br>')}</p>")


def email_sequence(corps: str, lien_desinscription: str) -> tuple[str, str]:
    """(html, texte) d'un pas e-mail : le texte rendu (variables déjà remplacées), puis le pied
    avec la raison du message et le lien de désinscription."""
    paragraphes = [p.strip() for p in corps.split("\n\n") if p.strip()]
    interieur = "".join(_paragraphe_avec_liens(p) for p in paragraphes)
    preentete = paragraphes[0][:120] if paragraphes else ""
    texte = f"{corps.strip()}\n\n--\n{RAISON}\nSe désinscrire : {lien_desinscription}"
    return mise_en_page(preentete, interieur, lien_desinscription), texte


def page(titre_page: str, message: str) -> str:
    """Page web minimale aux couleurs MERCI (désinscription)."""
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(titre_page)}</title></head>
<body style="margin:0;padding:64px 16px;background:{CREME};font-family:{FONT};color:{ENCRE};">
<main style="max-width:480px;margin:0 auto;background:#ffffff;border:1px solid {FILET};border-radius:8px;padding:32px 28px;">
<img src="{html.escape(logo_url(), quote=True)}" width="96" alt="MERCI" style="display:block;margin:0 0 20px;">
<p style="margin:0;font-size:17px;line-height:26px;">{html.escape(message, quote=False)}</p>
</main>
</body></html>"""
