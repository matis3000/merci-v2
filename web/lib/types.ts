// Types du contrat d'API (section 4 du dossier d'architecture), recopiés tels quels.

export type Iso = string;              // "2026-10-12T07:15:00Z"
export type Jour = string;             // "2026-10-12"
export type PipelineCle = "donateurs" | "entreprises" | "associations";
export type TypeContact = "donateur" | "association" | "entreprise";
export type Source = "landing" | "prospection" | "import" | "manuel";
export type SequenceCle = "donateur-bienvenue" | "donateur-pilote" | "entreprise-entrante" | "association-bienvenue" | "entreprise-prospection";
export type Canal = "email" | "linkedin_invitation" | "linkedin_message";
export type EtapeParcours = "attirer" | "capturer" | "suivre" | "relancer" | "convertir" | "fideliser";

export interface Membre { id: number; email: string; prenom: string; role: "admin" | "equipe"; actif: boolean }

export interface Etape { cle: string; nom: string }
export interface PipelineDef { cle: PipelineCle; nom: string; etapes: Etape[]; etape_perdue: Etape }

export interface Cible { genre: "contact" | "organisation"; id: number }

/** État de séquence affiché partout (carte, ligne, fiche). */
export interface EtatSequence {
  inscription_id: number;
  sequence: SequenceCle;
  nom: string;
  pas: number;
  total: number;
  etat: "due" | "active" | "pause" | "echec" | "arret" | "fini";
  prochain_envoi_at: Iso | null;
  attente: "acceptation" | "plafond" | "creneau" | "linkedin_deconnecte" | null;
  raison: string | null;
}

export interface Organisation {
  id: number; type: "entreprise" | "association"; nom: string; siren: string | null;
  ville: string | null; code_postal: string | null; departement: string | null;
  tranche_effectif: string | null; effectif_libelle: string | null;
  naf_code: string | null; naf_libelle: string | null; site_web: string | null;
  note: number | null; raisons: string[];
}

export interface Contact {
  id: number; type: TypeContact; prenom: string | null; nom: string | null;
  email: string | null; telephone: string | null; poste: string | null; ville: string | null;
  linkedin_url: string | null; source: Source; source_detail: string | null;
  consentement_at: Iso | null; consentement_texte: string | null;
  desinscrit_at: Iso | null; pause: boolean; cree_at: Iso;
}

export interface AffaireResume { id: number; pipeline: PipelineCle; etape: Etape }
export interface Affaire extends AffaireResume {
  etape_depuis: Iso; etapes_possibles: Etape[];
  responsable: Membre | null; montant_mensuel: string | null; perdue_raison: string | null;
}

export interface Activite {
  id: number; type: string; canal: "email" | "linkedin" | "systeme" | "equipe";
  titre: string; texte: string | null; fort: boolean;
  auteur: { id: number; prenom: string } | null; cree_at: Iso;
}

export interface PasDef {
  numero: number; canal: Canal; delai_libelle: string;
  titre: string; sujet: string | null; corps: string; personnalise: boolean;
}
export interface SequenceDef {
  cle: SequenceCle; nom: string; public: "Donateurs" | "Entreprises"; declencheur: string;
  coupee: boolean; pas: PasDef[];
}

export interface Fiche {
  genre: "contact" | "organisation"; id: number;
  contact: Contact | null; organisation: Organisation | null; affaire: Affaire | null;
  autres_contacts: { id: number; nom_affiche: string; poste: string | null }[];
  sequence: null | {
    etat: EtatSequence; definition: SequenceDef;
    envois: { pas: number; statut: string; envoye_at: Iso | null }[];
  };
  sequences_possibles: SequenceCle[];
  activites: Activite[];
  activites_suivant: number | null;
  hubspot: SynchroHubspot | null;
}

// ---------- Synchro HubSpot (lot L8) ----------

export interface SynchroHubspot { etat: "a_synchroniser" | "ok" | "erreur"; message: string | null; synchro_at: Iso | null }

/** Correspondance des étapes : {pipeline: {clé d'étape MERCI: id d'étape HubSpot}}. */
export type HubspotEtapes = Record<PipelineCle, Record<string, string>>;

export interface HubspotEtat {
  etat: "non_connecte" | "connecte" | "erreurs";
  compteurs: { synchronises: number; en_attente: number; en_erreur: number };
  dernieres_erreurs: {
    objet_type: "contact" | "organisation" | "affaire"; objet_id: number; nom: string;
    message: string; at: Iso; nouvel_essai_at: Iso | null;
  }[];
  derniere_synchro_at: Iso | null;
}

export interface Ligne {
  genre: "contact" | "organisation"; id: number; nom_affiche: string; sous_titre: string;
  type: TypeContact; email: string | null; organisation: { id: number; nom: string } | null;
  ville: string | null; source: Source; source_detail: string | null;
  affaire: AffaireResume | null; note: number | null; sequence: EtatSequence | null;
  derniere_activite: { titre: string; at: Iso } | null;
}

export interface Carte {
  affaire_id: number; cible: Cible; titre: string; sous_titre: string;
  note: number | null; sequence: EtatSequence | null;
}

export interface Passage {
  id: number; declencheur: "cron" | "manuel"; statut: "en_cours" | "fini" | "erreur";
  debut_at: Iso; fin_at: Iso | null; entreprises_vues: number; nouvelles: number;
  decideurs: number; en_sequence: number; erreur: string | null;
}

// ---------- Réponses des routes ----------

export interface CoqueRep {
  aujourdhui: Jour;
  nb_contacts: number;
  nb_sequences_en_cours: number;
  relances_en_pause: boolean;
  creneau: { jours: number[]; debut: number; fin: number };
  linkedin: { fournisseur: string; etat: "ok" | "a_reconnecter" | "non_configure" | "inconnu" };
  nb_echecs: number;
}

export interface AccueilRep {
  parcours: {
    etapes: { cle: EtapeParcours; nom: string; info: string }[];
    publics: {
      pipeline: "donateurs" | "entreprises"; nom: string;
      cases: Record<EtapeParcours, { n: number; detail: { libelle: string; n: number }[] }>;
    }[];
  };
  a_faire: {
    type: "reponse" | "demo_a_planifier" | "demo_a_preparer" | "signature" | "activer_salaries" | "appeler_association" | "echec";
    titre: string; sous_titre: string; cible: Cible;
    pastille: "linkedin" | "calendrier" | "telephone" | "coche" | "attention"; ton: "vert" | "poudre" | null;
    bouton: string; depuis: Iso;
  }[];
  relances: { partent_aujourdhui: number; en_cours: number; en_pause: number; en_echec: number };
  arrives_landing: { cible: Cible; nom_affiche: string; type: TypeContact; organisation_nom: string | null; source_detail: string | null; cree_at: Iso }[];
}

export interface PipelineRep {
  pipeline: PipelineDef;
  colonnes: { etape: Etape; cartes: Carte[] }[];
  perdus: number;
  compte_par_pipeline: Record<PipelineCle, number>;
}

export interface ContactsRep {
  total: number; page: number; par_page: number;
  resume: { landing: number; prospection: number };
  lignes: Ligne[];
}

export interface FiltresContacts {
  type?: TypeContact; source?: Source; pipeline?: PipelineCle; etape?: string;
  note_min?: number; sequence?: SequenceCle; etat_sequence?: EtatSequence["etat"];
  q?: string; page?: number; par_page?: number;
}

export interface NouveauContact {
  type: TypeContact; prenom?: string; nom?: string; email?: string; telephone?: string; poste?: string;
  linkedin_url?: string; ville?: string; organisation_nom?: string; source_detail?: string;
}

export interface ImportRep { crees: number; mis_a_jour: number; ignores: number; erreurs: { ligne: number; raison: string }[] }

export type SequenceListe = SequenceDef & {
  actifs: number;
  stats: { envoyes: number; ouverts: number | null; acceptees: number | null; reponses: number };
};

export interface CibleProspection { departements: string[]; effectif_min: number; postes: string[]; plafond_jour: number; seuil: number }

export interface ProspectionRep {
  cible: CibleProspection;
  dernier_passage: Passage | null;
  en_cours: boolean;
  invitations_aujourdhui: number;
  a_rechercher: number;
  entreprises: {
    organisation_id: number; nom: string; ville: string | null; effectif_libelle: string | null;
    naf_libelle: string | null; decideur: { contact_id: number; nom: string; poste: string | null } | null;
    note: number | null;
    suite: "en_sequence" | "file_plafond" | "a_traiter" | "deja_en_cours" | "a_rechercher";
    suite_libelle: string;
  }[];
}

export interface Creneau { jours: number[]; debut: number; fin: number }

export interface ReglagesRep {
  relances_en_pause: boolean;
  creneau: Creneau & { fuseau: "Europe/Paris" };
  expediteur: { nom: string; email: string }; reponse_a: string | null;
  lien_rdv: string | null; lien_creation_compte: string | null;
  pilote_ouvert_at: Iso | null;
  connexions: {
    landing: { derniere_inscription_at: Iso | null; origines: string[] };
    email: { fournisseur: "resend" | "console"; etat: "ok" | "non_configure" | "erreur"; derniere_erreur_at: Iso | null };
    linkedin: { fournisseur: "connectsafely" | "factice"; etat: "ok" | "a_reconnecter" | "non_configure" | "inconnu" };
    app_merci: { cle_configuree: boolean; cle_masquee: string | null };
  };
  equipe: Membre[];
  hubspot_etapes: HubspotEtapes;
}

export interface ReglagesCorps {
  relances_en_pause?: boolean; creneau?: Creneau; expediteur?: { nom: string; email: string };
  reponse_a?: string | null; lien_rdv?: string | null; lien_creation_compte?: string | null;
  hubspot_etapes?: Partial<HubspotEtapes>;
}
