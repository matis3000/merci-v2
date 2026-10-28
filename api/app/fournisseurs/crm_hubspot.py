"""CrmExterneProvider HubSpot (lot L8) : appels httpx, jeton d'app privée en `Authorization: Bearer`.

Points d'accès confirmés le 13/10/2026 dans la documentation officielle et dans les spécifications
OpenAPI publiées par HubSpot (dépôt HubSpot-public-api-spec-collection) :
- contacts v3 : `POST /crm/v3/objects/contacts/batch/upsert` (`idProperty: "email"`, réponse
  `{status, results: [{id, new, ...}]}`), `POST /crm/v3/objects/contacts` (201 `{id}`),
  `PATCH /crm/v3/objects/contacts/{id}` ;
- companies et deals v3 : `POST /crm/v3/objects/{companies|deals}`, `PATCH .../{id}` ; création :
  corps `{properties, associations}` (`associations` requis par le schéma, liste vide ici) ;
- deals : `pipeline` = `default` pour le pipeline par défaut, `dealstage` = identifiant interne ;
- pipelines v3 : `GET /crm/v3/pipelines/deals/default` (`{id, label, stages: [{id, label, displayOrder}]}`) ;
- associations v4 : `PUT /crm/v4/objects/{from}/{id}/associations/default/{to}/{id}` (types
  d'objets par identifiant : 0-1 contacts, 0-2 companies, 0-3 deals) ;
- propriétés v3 : `GET/POST /crm/v3/properties/{objet}` et `GET/POST /crm/v3/properties/{objet}/groups`
  (création : `name, label, type, fieldType, groupName`, `options` pour les listes) ;
- dates (`type: date`) au format `AAAA-MM-JJ` ; chaîne vide = valeur effacée ;
- 429 : limite de débit (10 secondes glissantes ou jour), à reprendre plus tard.
Le jeton n'apparaît jamais dans un message d'erreur, un journal ou `repr`.
"""
from __future__ import annotations

import httpx

from .base import ErreurFournisseur, LimiteDebit, ObjetIntrouvable, ProprieteCrm

URL_BASE = "https://api.hubapi.com"
TYPES_ASSOCIATION = {"contacts": "0-1", "companies": "0-2", "deals": "0-3"}
OBJETS = ("contacts", "companies", "deals")


class HubspotCrmProvider:
    nom = "hubspot"
    connecte = True

    def __init__(self, jeton: str, transport: httpx.BaseTransport | None = None, timeout: float = 10.0):
        # Le jeton ne vit que dans l'en-tête du client (aucun attribut lisible ni affichable).
        self._client = httpx.Client(base_url=URL_BASE, timeout=timeout, transport=transport,
                                    headers={"Authorization": f"Bearer {jeton}", "Content-Type": "application/json"})

    def __repr__(self) -> str:
        return "HubspotCrmProvider(jeton=••••)"

    # ------------------------------------------------------------------ transport

    def _expurger(self, texte: str) -> str:
        jeton = self._client.headers.get("Authorization", "").removeprefix("Bearer ")
        return texte.replace(jeton, "••••") if jeton else texte

    def _appel(self, methode: str, chemin: str, corps: dict | None = None) -> dict:
        try:
            rep = self._client.request(methode, chemin, json=corps)
        except httpx.HTTPError as e:
            raise ErreurFournisseur(f"HubSpot injoignable ({type(e).__name__})") from None
        if rep.status_code < 300:
            try:
                return rep.json() if rep.content else {}
            except ValueError:
                raise ErreurFournisseur("Réponse HubSpot non vérifiée : JSON illisible") from None
        code = rep.status_code
        if code == 401:
            raise ErreurFournisseur("HubSpot refuse le jeton (401) : vérifiez HUBSPOT_TOKEN")
        if code == 403:
            raise ErreurFournisseur("HubSpot refuse l'accès (403) : vérifiez les droits de l'app privée")
        if code == 404:
            raise ObjetIntrouvable("Objet introuvable dans HubSpot (404)")
        if code == 429:
            raise LimiteDebit("Limite de débit HubSpot atteinte (429) : nouvel essai plus tard")
        if code >= 500:
            raise ErreurFournisseur(f"HubSpot indisponible (HTTP {code})")
        try:
            detail = str(rep.json().get("message") or "")
        except ValueError:
            detail = ""
        detail = self._expurger(detail)[:300]
        raise ErreurFournisseur(f"HubSpot refuse les données (HTTP {code})" + (f" : {detail}" if detail else ""))

    @staticmethod
    def _ident(rep: dict) -> str:
        ident = rep.get("id")
        if not ident:
            raise ErreurFournisseur("Réponse HubSpot non vérifiée : aucun identifiant renvoyé")
        return str(ident)

    # ------------------------------------------------------------------ propriétés

    def assurer_proprietes(self, groupe: tuple[str, str], proprietes: list[ProprieteCrm]) -> None:
        nom_groupe, libelle_groupe = groupe
        for objet in OBJETS:
            a_creer = [p for p in proprietes if p.objet == objet]
            if not a_creer:
                continue
            # https://developers.hubspot.com/docs/guides/api/crm/properties (GET groups : "Read all property groups")
            groupes = {g.get("name") for g in self._appel("GET", f"/crm/v3/properties/{objet}/groups").get("results", [])}
            if nom_groupe not in groupes:
                # https://developers.hubspot.com/docs/guides/api/crm/properties (POST groups : "Create a property group")
                self._appel("POST", f"/crm/v3/properties/{objet}/groups", {"name": nom_groupe, "label": libelle_groupe})
            # https://developers.hubspot.com/docs/guides/api/crm/properties (GET : "Read all properties")
            existantes = {p.get("name") for p in self._appel("GET", f"/crm/v3/properties/{objet}").get("results", [])}
            for p in a_creer:
                if p.nom in existantes:
                    continue
                corps = {"name": p.nom, "label": p.libelle, "type": p.type, "fieldType": p.champ, "groupName": nom_groupe}
                if p.options:
                    corps["options"] = [{"value": v, "label": lib, "displayOrder": i, "hidden": False}
                                        for i, (v, lib) in enumerate(p.options)]
                # https://developers.hubspot.com/docs/guides/api/crm/properties (POST : "Create a property")
                self._appel("POST", f"/crm/v3/properties/{objet}", corps)

    # ------------------------------------------------------------------ objets

    def upsert_contact(self, email: str, proprietes: dict[str, str]) -> str:
        # https://developers.hubspot.com/docs/api-reference/crm-contacts-v3/batch/post-crm-v3-objects-contacts-batch-upsert
        rep = self._appel("POST", "/crm/v3/objects/contacts/batch/upsert",
                          {"inputs": [{"idProperty": "email", "id": email, "properties": proprietes}]})
        resultats = rep.get("results") or []
        if len(resultats) != 1:
            raise ErreurFournisseur("Réponse HubSpot non vérifiée : upsert sans résultat unique")
        return self._ident(resultats[0])

    def creer(self, objet: str, proprietes: dict[str, str]) -> str:
        # Contacts : https://developers.hubspot.com/docs/api-reference/crm-contacts-v3/batch/post-crm-v3-objects-contacts-batch-upsert
        # Companies : https://developers.hubspot.com/docs/guides/api/crm/objects/companies
        # Deals : https://developers.hubspot.com/docs/guides/api/crm/objects/deals
        return self._ident(self._appel("POST", f"/crm/v3/objects/{self._objet(objet)}",
                                       {"properties": proprietes, "associations": []}))

    def modifier(self, objet: str, ident: str, proprietes: dict[str, str]) -> None:
        # Mêmes pages que `creer` (sections « Update ») : PATCH /crm/v3/objects/{objet}/{id}
        self._appel("PATCH", f"/crm/v3/objects/{self._objet(objet)}/{ident}", {"properties": proprietes})

    def associer(self, objet: str, ident: str, vers: str, vers_ident: str | None) -> None:
        if not vers_ident:
            raise ErreurFournisseur("Association impossible : objet lié pas encore envoyé à HubSpot")
        de, a = TYPES_ASSOCIATION[self._objet(objet)], TYPES_ASSOCIATION[self._objet(vers)]
        # https://developers.hubspot.com/docs/guides/api/crm/associations/associations-v4 ("Associate records without a label")
        self._appel("PUT", f"/crm/v4/objects/{de}/{ident}/associations/default/{a}/{vers_ident}")

    def etapes_pipeline(self) -> list[dict[str, str]]:
        # https://developers.hubspot.com/docs/guides/api/crm/pipelines ("Return a pipeline by ID", pipeline `default`)
        rep = self._appel("GET", "/crm/v3/pipelines/deals/default")
        etapes = rep.get("stages")
        if not isinstance(etapes, list):
            raise ErreurFournisseur("Réponse HubSpot non vérifiée : pipeline sans liste d'étapes")
        etapes = sorted((e for e in etapes if not e.get("archived")), key=lambda e: e.get("displayOrder", 0))
        return [{"id": str(e["id"]), "label": str(e.get("label") or e["id"])} for e in etapes if e.get("id")]

    @staticmethod
    def _objet(objet: str) -> str:
        if objet not in OBJETS:
            raise ErreurFournisseur(f"Type d'objet HubSpot non vérifié : {objet}")
        return objet
