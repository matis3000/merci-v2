import { texteEtat } from "@/lib/format";
import type { EtatSequence as Etat } from "@/lib/types";

/** Libellé d'état de séquence (classes .c-etat de la preview). */
export function EtatSequence({ s }: { s: Etat | null }) {
  if (!s) return <span className="c-etat">Pas de séquence</span>;
  const classe = s.etat === "fini" ? "arret" : s.etat;
  return <span className={`c-etat c-etat--${classe}`}>{texteEtat(s)}</span>;
}
