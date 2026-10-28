"use client";

import type { CSSProperties, ReactNode } from "react";

/** Interrupteur plat .c-switch : libellé visible optionnel, libellé accessible obligatoire. */
export function Interrupteur({ actif, onChange, aria, children, style, desactive }: {
  actif: boolean;
  onChange: (actif: boolean) => void;
  aria: string;
  children?: ReactNode;
  style?: CSSProperties;
  desactive?: boolean;
}) {
  return (
    <label className="c-switch" style={style}>
      {children}
      <input type="checkbox" checked={actif} disabled={desactive} aria-label={aria} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}
