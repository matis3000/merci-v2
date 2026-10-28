"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// Chargement d'une ressource de l'API, rechargé quand `cle` change.
// `cle` à null : rien n'est chargé. Après une mutation, appeler `recharger()`.
export function useDonnees<T>(cle: string | null, charger: () => Promise<T>) {
  const [donnees, setDonnees] = useState<T | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [chargement, setChargement] = useState(cle !== null);
  const chargeur = useRef(charger);
  chargeur.current = charger;
  const [tour, setTour] = useState(0);

  useEffect(() => {
    if (cle === null) return;
    let actif = true;
    setChargement(true);
    chargeur.current()
      .then((d) => { if (actif) { setDonnees(d); setErreur(null); } })
      .catch((e: unknown) => { if (actif) setErreur(e instanceof Error ? e.message : "Erreur de chargement"); })
      .finally(() => { if (actif) setChargement(false); });
    return () => { actif = false; };
  }, [cle, tour]);

  const recharger = useCallback(() => setTour((t) => t + 1), []);
  return { donnees, erreur, chargement, recharger, setDonnees };
}
