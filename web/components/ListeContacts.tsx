import Link from "next/link";
import { classeInitiales, depuis, initiales, libelleSource, majuscule, nomPipeline } from "@/lib/format";
import type { Ligne } from "@/lib/types";
import { EtatSequence } from "./EtatSequence";
import { lienCible } from "./Kanban";
import { Note } from "./Note";

/** Tableau des contacts (.c-liste), lignes de la preview. */
export function ListeContacts({ lignes, vide }: { lignes: Ligne[]; vide: string }) {
  return (
    <div className="c-liste" role="table" aria-label="Contacts">
      <div className="c-ligne c-ligne--tete" role="row">
        <span>Contact</span><span>Pipeline</span><span>Source</span><span>Note</span><span>Séquence</span><span>Dernière activité</span>
      </div>
      {lignes.length ? lignes.map((l) => (
        <Link key={`${l.genre}-${l.id}`} className="c-ligne" role="row" href={lienCible(l)}>
          <span className="c-qui-cell">
            <span className={`c-initiales${classeInitiales(l.type)}`}>{initiales(l.nom_affiche)}</span>
            <span><b>{l.nom_affiche}</b><span>{l.sous_titre}</span></span>
          </span>
          <span className="c-cell">
            {l.affaire ? <>{nomPipeline(l.affaire.pipeline)}<small>{l.affaire.etape.nom}</small></> : <span className="c-cell--muet">Aucun</span>}
          </span>
          <span className="c-cell">{libelleSource(l.source)}{l.source_detail ? <small>{majuscule(l.source_detail)}</small> : null}</span>
          <span className="c-cell">{l.note != null ? <Note n={l.note} /> : <span className="c-cell--muet">Sans</span>}</span>
          <span className="c-cell"><EtatSequence s={l.sequence} /></span>
          <span className="c-cell c-cell--muet">
            {l.derniere_activite ? <>{majuscule(depuis(l.derniere_activite.at))}<small>{l.derniere_activite.titre}</small></> : "Aucune activité"}
          </span>
        </Link>
      )) : (
        <p className="c-ligne--vide">{vide}</p>
      )}
    </div>
  );
}
