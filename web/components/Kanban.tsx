"use client";

// Colonnes du pipeline, glisser-déposer natif HTML5 : la carte change de colonne tout de suite,
// puis PATCH /affaires/{id}. En cas d'erreur, la carte revient à sa place.
import Link from "next/link";
import { useEffect, useState } from "react";
import type { Carte, PipelineRep } from "@/lib/types";
import { EtatSequence } from "./EtatSequence";
import { Note } from "./Note";

type Colonnes = PipelineRep["colonnes"];

export const lienCible = (c: { genre: "contact" | "organisation"; id: number }) =>
  c.genre === "contact" ? `/contacts/${c.id}` : `/organisations/${c.id}`;

function deplacer(colonnes: Colonnes, affaireId: number, etape: string): Colonnes {
  let carte: Carte | undefined;
  const sans = colonnes.map((col) => {
    const trouvee = col.cartes.find((c) => c.affaire_id === affaireId);
    if (trouvee) carte = trouvee;
    return trouvee ? { ...col, cartes: col.cartes.filter((c) => c !== trouvee) } : col;
  });
  if (!carte) return colonnes;
  const deplacee = carte;
  return sans.map((col) => (col.etape.cle === etape ? { ...col, cartes: [deplacee, ...col.cartes] } : col));
}

export function Kanban({ colonnes, onDeplacer }: {
  colonnes: Colonnes;
  onDeplacer: (affaireId: number, etape: string) => Promise<void>;
}) {
  const [cols, setCols] = useState(colonnes);
  const [tenu, setTenu] = useState<number | null>(null);
  const [survol, setSurvol] = useState<string | null>(null);
  useEffect(() => setCols(colonnes), [colonnes]);

  async function deposer(etape: string) {
    setSurvol(null);
    if (tenu === null) return;
    const origine = cols.find((col) => col.cartes.some((c) => c.affaire_id === tenu));
    setTenu(null);
    if (!origine || origine.etape.cle === etape) return;
    const avant = cols;
    setCols(deplacer(cols, tenu, etape));
    try {
      await onDeplacer(tenu, etape);
    } catch {
      setCols(avant);
    }
  }

  return (
    <div className="c-colonnes" style={{ ["--n" as string]: cols.length }}>
      {cols.map((col) => (
        <section key={col.etape.cle} className={`c-colonne${survol === col.etape.cle ? " c-survol" : ""}`} aria-label={col.etape.nom}
          onDragOver={(e) => { if (tenu === null) return; e.preventDefault(); setSurvol(col.etape.cle); }}
          onDragLeave={() => setSurvol((s) => (s === col.etape.cle ? null : s))}
          onDrop={(e) => { e.preventDefault(); deposer(col.etape.cle); }}>
          <div className="c-colonne__tete"><b>{col.etape.nom}</b><span className="c-compte">{col.cartes.length}</span></div>
          <div className="c-cartes">
            {col.cartes.length ? col.cartes.map((c) => (
              <Link key={c.affaire_id} className={`c-carte${tenu === c.affaire_id ? " c-tient" : ""}`} href={lienCible(c.cible)} draggable
                onDragStart={(e) => { setTenu(c.affaire_id); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", String(c.affaire_id)); }}
                onDragEnd={() => { setTenu(null); setSurvol(null); }}>
                <div className="c-carte__haut"><b>{c.titre}</b><Note n={c.note} /></div>
                <span>{c.sous_titre}</span>
                <div className="c-carte__pied"><EtatSequence s={c.sequence} /></div>
              </Link>
            )) : <p className="c-vide">Glissez une carte ici</p>}
          </div>
        </section>
      ))}
    </div>
  );
}
