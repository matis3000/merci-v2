import { classeNote } from "@/lib/format";

/** Pastille de note de prospection n/10 ; rien si la note est inconnue. */
export function Note({ n }: { n: number | null }) {
  if (n == null) return null;
  return <span className={`c-note c-note--${classeNote(n)}`}>{n}/10</span>;
}
