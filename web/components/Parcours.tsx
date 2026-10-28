import Link from "next/link";
import type { AccueilRep } from "@/lib/types";

type Detail = { libelle: string; n: number }[];

// Même règle que la preview : "Personne" à vide ; Attirer montre les deux premières sources.
function resume(detail: Detail, attirer: boolean): string {
  const tri = [...detail].sort((a, b) => b.n - a.n);
  if (!tri.length) return "Personne";
  if (attirer) return tri.slice(0, 2).map((d) => `${d.libelle} ${d.n}`).join(", ");
  return tri.map((d) => (tri.length > 1 ? `${d.libelle} ${d.n}` : d.libelle)).join(", ");
}

/** Grille du parcours client : 6 étapes x 2 publics. */
export function Parcours({ parcours }: { parcours: AccueilRep["parcours"] }) {
  const etapes = parcours.etapes;
  return (
    <section className="c-parcours" aria-labelledby="parcours-titre">
      <h2 className="c-cache" id="parcours-titre">Parcours client</h2>
      <div className="c-parcours__grille">
        <div />
        {etapes.map((e) => (
          <div className="c-parcours__etape" key={e.cle}><b>{e.nom}</b><span>{e.info}</span></div>
        ))}
        <div />
        <div className="c-parcours__piste">
          {etapes.map((e, i) => <i key={e.cle} style={{ left: `${((i + 0.5) / etapes.length) * 100}%` }} />)}
        </div>
        {parcours.publics.map((p) => [
          <div className="c-parcours__public" key={p.pipeline}>{p.nom}</div>,
          ...etapes.map((e) => {
            const v = p.cases[e.cle];
            return (
              <Link key={p.pipeline + e.cle} className={`c-parcours__case${v.n === 0 ? " c-parcours__case--vide" : ""}`} href={`/pipelines?p=${p.pipeline}`}>
                <strong>{v.n}</strong><small>{resume(v.detail, e.cle === "attirer")}</small>
              </Link>
            );
          }),
        ])}
      </div>
    </section>
  );
}
