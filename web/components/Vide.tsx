/** Message d'état vide ; la classe dépend de la zone (liste, colonne, bloc). */
export function Vide({ children, classe = "c-vide" }: { children: string; classe?: string }) {
  return <p className={classe}>{children}</p>;
}

/** Chargement ou erreur d'une page, avant que les données n'arrivent. */
export function Attente({ erreur }: { erreur: string | null }) {
  if (erreur) return <p className="c-erreur" role="alert">{erreur}</p>;
  return <p className="c-chargement" role="status">Chargement…</p>;
}
