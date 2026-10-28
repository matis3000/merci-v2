"use client";

// Fil d'activité de la fiche (.c-fil) et formulaire de note (.c-noter).
import { useState, type FormEvent } from "react";
import { depuis, majuscule } from "@/lib/format";
import type { Activite } from "@/lib/types";
import { Icone, type NomIcone } from "./Icone";

function icone(a: Activite): NomIcone {
  if (a.canal === "equipe") return a.type === "appel" ? "telephone" : "contacts";
  return a.canal;
}

export function FilActivite({ activites, suivant, onAjouter, onPlus }: {
  activites: Activite[];
  suivant: number | null;
  onAjouter: (texte: string) => Promise<void>;
  onPlus: () => Promise<void>;
}) {
  const [texte, setTexte] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  async function ajouter(e: FormEvent) {
    e.preventDefault();
    if (!texte.trim()) return;
    setEnvoi(true);
    setErreur(null);
    try {
      await onAjouter(texte.trim());
      setTexte("");
    } catch (err) {
      setErreur(err instanceof Error ? err.message : "Note non enregistrée.");
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <section className="c-bloc" aria-labelledby="fil-titre">
      <div className="c-bloc__tete"><h2 className="c-h2" id="fil-titre">Activité</h2></div>
      <form className="c-noter" onSubmit={ajouter}>
        <input placeholder="Ajouter une note, un appel, un compte rendu" aria-label="Ajouter une note" value={texte} maxLength={5000}
          onChange={(e) => setTexte(e.target.value)} />
        <button className="c-btn c-btn--s" type="submit" disabled={envoi}>Ajouter</button>
      </form>
      {erreur ? <p className="c-erreur" role="alert">{erreur}</p> : null}
      {activites.length ? (
        <ol className="c-fil">
          {activites.map((a) => (
            <li key={a.id}>
              <span className={`c-pastille${a.fort ? " c-pastille--vert" : ""}`}><Icone nom={icone(a)} /></span>
              <div>
                <b>{a.titre}</b>
                <time dateTime={a.cree_at}>{majuscule(depuis(a.cree_at))}{a.auteur ? `, par ${a.auteur.prenom}` : ""}</time>
                {a.texte ? <p className={a.fort ? "c-citation" : undefined}>{a.texte}</p> : null}
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="m-petit">Aucune activité.</p>
      )}
      {suivant !== null ? <button className="c-btn c-btn--s" type="button" onClick={onPlus}>Voir les activités plus anciennes</button> : null}
    </section>
  );
}
