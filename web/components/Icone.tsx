// Icônes de la preview (preview/crm.js, objet P) : trait 1.7, couleur du texte.
import type { ReactNode } from "react";

const P = {
  accueil: <path d="M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1z" />,
  pipelines: <><rect x="4" y="4.5" width="4.5" height="15" rx="2" /><rect x="10" y="4.5" width="4.5" height="10" rx="2" /><rect x="16" y="4.5" width="4" height="6.5" rx="2" /></>,
  contacts: <><circle cx="9" cy="8.5" r="3.2" /><path d="M3.5 19c.6-3.2 2.9-5 5.5-5s4.9 1.8 5.5 5" /><circle cx="17" cy="9.5" r="2.4" /><path d="M16 14.2c2.3.1 4 1.6 4.5 4.3" /></>,
  sequences: <><path d="M5 6h9M5 12h14M5 18h7" /><circle cx="18" cy="6" r="1.6" /><circle cx="15" cy="18" r="1.6" /></>,
  prospection: <><circle cx="11" cy="11" r="6.2" /><path d="m16 16 4 4" /></>,
  reglages: <><circle cx="12" cy="12" r="3" /><path d="M12 3v2.2M12 18.8V21M3 12h2.2M18.8 12H21M5.6 5.6l1.6 1.6M16.8 16.8l1.6 1.6M5.6 18.4l1.6-1.6M16.8 7.2l1.6-1.6" /></>,
  email: <><rect x="3.5" y="5.5" width="17" height="13" rx="3" /><path d="m4.5 7.5 7.5 5.5 7.5-5.5" /></>,
  linkedin: <><rect x="3.5" y="3.5" width="17" height="17" rx="4" /><path d="M8 10.5V16M8 7.8v.1M11.5 16v-5.5M11.5 13c0-1.6 1-2.6 2.4-2.6s2.1 1 2.1 2.6V16" /></>,
  systeme: <><path d="M12 4v3M12 17v3M4 12h3M17 12h3" /><circle cx="12" cy="12" r="4" /></>,
  retour: <path d="M14.5 6 8.5 12l6 6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  pause: <><rect x="6.5" y="5" width="3.6" height="14" rx="1.4" /><rect x="13.9" y="5" width="3.6" height="14" rx="1.4" /></>,
  lecture: <path d="M8 5.5v13l10.5-6.5z" />,
  calendrier: <><rect x="4" y="5.5" width="16" height="14" rx="3" /><path d="M4 10h16M8.5 3.5v4M15.5 3.5v4" /></>,
  telephone: <path d="M6.5 4h3l1.5 4-2 1.3a10 10 0 0 0 5.7 5.7l1.3-2 4 1.5v3a2 2 0 0 1-2 2A15 15 0 0 1 4.5 6a2 2 0 0 1 2-2z" />,
  fleche: <path d="M7 17 17 7M9 7h8v8" />,
  import: <path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14" />,
  export: <path d="M12 15V4M7.5 8.5 12 4l4.5 4.5M5 19.5h14" />,
  attention: <><path d="M12 4.5 21 19.5H3z" /><path d="M12 10v4M12 16.8v.1" /></>,
  coche: <path d="m6 12.5 4 4 8-9" />,
} satisfies Record<string, ReactNode>;

export type NomIcone = keyof typeof P;

export function Icone({ nom }: { nom: NomIcone }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {P[nom]}
    </svg>
  );
}
