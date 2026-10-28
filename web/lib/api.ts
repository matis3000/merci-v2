// Client typé : une fonction par route d'équipe de la section 4.
// Toutes les requêtes passent par /api (réécriture Next vers l'API), cookie de session inclus.
import type {
  AccueilRep, Activite, Affaire, CibleProspection, ContactsRep, CoqueRep, EtatSequence, Fiche,
  FiltresContacts, HubspotEtat, ImportRep, Membre, NouveauContact, PasDef, PipelineCle, PipelineDef, PipelineRep,
  ProspectionRep, ReglagesCorps, ReglagesRep, SequenceCle, SequenceDef, SequenceListe,
} from "./types";

export class ErreurApi extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

// Ces routes répondent 401 pour un lien invalide : on affiche le message au lieu de rediriger.
const SANS_REDIRECTION = ["/auth/lien", "/auth/verifier"];

async function appel<T>(chemin: string, init: RequestInit = {}): Promise<T> {
  const multipart = init.body instanceof FormData;
  const rep = await fetch("/api" + chemin, {
    credentials: "include",
    ...init,
    headers: multipart ? init.headers : { "Content-Type": "application/json", ...init.headers },
  });
  if (rep.status === 401 && !SANS_REDIRECTION.includes(chemin)) {
    window.location.assign("/connexion");
    throw new ErreurApi(401, "Session expirée, reconnectez-vous.");
  }
  if (!rep.ok) {
    let message = "Une erreur est survenue, réessayez.";
    try {
      const corps = await rep.json();
      if (typeof corps.detail === "string") message = corps.detail;
      else if (Array.isArray(corps.detail)) message = "Certaines valeurs sont invalides, vérifiez le formulaire.";
    } catch {
      // réponse sans JSON : message générique
    }
    throw new ErreurApi(rep.status, message);
  }
  if (rep.status === 204) return undefined as T;
  return (await rep.json()) as T;
}

const json = (methode: string, corps?: unknown): RequestInit => ({
  method: methode,
  body: corps === undefined ? undefined : JSON.stringify(corps),
});

function requete(filtres: object): string {
  const p = new URLSearchParams();
  for (const [cle, valeur] of Object.entries(filtres)) {
    if (valeur !== undefined && valeur !== null && valeur !== "") p.set(cle, String(valeur));
  }
  const s = p.toString();
  return s ? "?" + s : "";
}

export const api = {
  auth: {
    lien: (email: string) => appel<{ ok: true; dev_lien?: string }>("/auth/lien", json("POST", { email })),
    verifier: (jeton: string) => appel<{ membre: Membre }>("/auth/verifier", json("POST", { jeton })),
    moi: () => appel<Membre>("/auth/moi"),
    deconnexion: () => appel<void>("/auth/deconnexion", json("POST")),
  },
  coque: () => appel<CoqueRep>("/coque"),
  accueil: () => appel<AccueilRep>("/accueil"),
  pipelines: {
    liste: () => appel<PipelineDef[]>("/pipelines"),
    voir: (cle: PipelineCle, q?: string) => appel<PipelineRep>(`/pipelines/${cle}${requete({ q })}`),
  },
  affaires: {
    modifier: (id: number, corps: { etape?: string; perdue_raison?: string; responsable_id?: number | null; montant_mensuel?: string | null }) =>
      appel<Affaire>(`/affaires/${id}`, json("PATCH", corps)),
  },
  contacts: {
    liste: (filtres: FiltresContacts) => appel<ContactsRep>(`/contacts${requete(filtres)}`),
    creer: (corps: NouveauContact) => appel<Fiche>("/contacts", json("POST", corps)),
    voir: (id: number) => appel<Fiche>(`/contacts/${id}`),
    modifier: (id: number, corps: Partial<Omit<NouveauContact, "type">> & { linkedin_provider_id?: string }) =>
      appel<Fiche>(`/contacts/${id}`, json("PATCH", corps)),
    activites: (id: number, avant?: number) =>
      appel<{ activites: Activite[]; suivant: number | null }>(`/contacts/${id}/activites${requete({ avant })}`),
    noter: (id: number, corps: { type: "note" | "appel"; texte: string }) =>
      appel<Activite>(`/contacts/${id}/activites`, json("POST", corps)),
    importer: (fichier: File) => {
      const f = new FormData();
      f.append("fichier", fichier);
      return appel<ImportRep>("/contacts/import", { method: "POST", body: f });
    },
    lienExport: (filtres: FiltresContacts) => `/api/contacts/export.csv${requete(filtres)}`,
    inscrire: (id: number, sequence: SequenceCle) =>
      appel<EtatSequence>(`/contacts/${id}/sequence`, json("POST", { sequence })),
    pause: (id: number, pause: boolean) =>
      appel<{ pause: boolean; sequence: EtatSequence | null }>(`/contacts/${id}/pause`, json("POST", { pause })),
  },
  organisations: {
    voir: (id: number) => appel<Fiche>(`/organisations/${id}`),
    modifier: (id: number, corps: { nom?: string; ville?: string; site_web?: string }) =>
      appel<Fiche>(`/organisations/${id}`, json("PATCH", corps)),
    activites: (id: number, avant?: number) =>
      appel<{ activites: Activite[]; suivant: number | null }>(`/organisations/${id}/activites${requete({ avant })}`),
    noter: (id: number, corps: { type: "note" | "appel"; texte: string }) =>
      appel<Activite>(`/organisations/${id}/activites`, json("POST", corps)),
  },
  sequences: {
    liste: () => appel<SequenceListe[]>("/sequences"),
    modifierPas: (cle: SequenceCle, numero: number, corps: { sujet?: string; corps: string }) =>
      appel<PasDef>(`/sequences/${cle}/pas/${numero}`, json("PUT", corps)),
    couper: (cle: SequenceCle, coupee: boolean) => appel<SequenceDef>(`/sequences/${cle}`, json("PATCH", { coupee })),
  },
  pilote: {
    ouvrir: () => appel<{ ouvert_at: string; inscrits: number }>("/pilote/ouvrir", json("POST")),
  },
  prospection: {
    voir: () => appel<ProspectionRep>("/prospection"),
    cible: (corps: CibleProspection) => appel<CibleProspection>("/prospection/cible", json("PUT", corps)),
    lancer: () => appel<{ passage_id: number }>("/prospection/lancer", json("POST")),
  },
  reglages: {
    voir: () => appel<ReglagesRep>("/reglages"),
    modifier: (corps: ReglagesCorps) => appel<ReglagesRep>("/reglages", json("PATCH", corps)),
  },
  hubspot: {
    etat: () => appel<HubspotEtat>("/hubspot/etat"),
    toutSynchroniser: () => appel<{ marques: number }>("/hubspot/tout-synchroniser", json("POST")),
    etapes: () => appel<{ etapes: { id: string; label: string }[] }>("/hubspot/etapes"),
  },
  equipe: {
    ajouter: (corps: { email: string; prenom: string; role: "admin" | "equipe" }) => appel<Membre>("/equipe", json("POST", corps)),
    modifier: (id: number, corps: { prenom?: string; role?: "admin" | "equipe"; actif?: boolean }) =>
      appel<Membre>(`/equipe/${id}`, json("PATCH", corps)),
  },
};
