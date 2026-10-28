"use client";

import type { ReactNode } from "react";

/** Groupe de boutons à choix unique (.c-seg), plat, sans animation. */
export function Segments<T extends string>({ libelle, valeur, options, onChoix }: {
  libelle: string;
  valeur: T;
  options: { cle: T; libelle: ReactNode }[];
  onChoix: (cle: T) => void;
}) {
  return (
    <div className="c-seg" role="group" aria-label={libelle}>
      {options.map((o) => (
        <button key={o.cle} type="button" aria-pressed={o.cle === valeur} onClick={() => onChoix(o.cle)}>
          {o.libelle}
        </button>
      ))}
    </div>
  );
}
