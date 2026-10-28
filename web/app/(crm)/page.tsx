"use client";

// Accueil, porté de `vAccueil` : parcours, à faire, relances, arrivés par la landing.
import Link from "next/link";
import { useCoque } from "@/components/Coque";
import { Icone } from "@/components/Icone";
import { lienCible } from "@/components/Kanban";
import { Parcours } from "@/components/Parcours";
import { Attente } from "@/components/Vide";
import { api } from "@/lib/api";
import { classeInitiales, depuis, initiales, jourLong, majuscule, pluriel, texteCreneau } from "@/lib/format";
import type { AccueilRep } from "@/lib/types";
import { useDonnees } from "@/lib/useDonnees";

export default function Accueil() {
  const { moi, coque } = useCoque();
  // Rechargé quand la pause générale change : les compteurs de relances en dépendent.
  const { donnees: d, erreur } = useDonnees<AccueilRep>(`accueil-${coque?.relances_en_pause ?? ""}`, api.accueil);
  if (!d) return <Attente erreur={erreur} />;

  const r = d.relances;
  const provenance = (x: AccueilRep["arrives_landing"][number]) =>
    x.type === "entreprise" ? x.organisation_nom ?? "Entreprise" : x.type === "association" ? "Association" : "Donateur";

  return (
    <>
      <div className="c-tete">
        <div>
          <h2 className="c-titre">Bonjour {moi.prenom}</h2>
          <p className="c-sous">
            {coque ? `${jourLong(coque.aujourdhui)} : ` : ""}
            <b>{pluriel(d.a_faire.length, "chose à faire", "choses à faire")}</b>, {pluriel(r.partent_aujourdhui, "relance part", "relances partent")} aujourd&apos;hui.
          </p>
        </div>
        <div className="c-actions">
          <Link className="c-btn" href="/contacts?action=importer"><Icone nom="import" />Importer</Link>
          <Link className="c-btn c-btn--plein" href="/contacts?action=ajouter"><Icone nom="plus" />Ajouter un contact</Link>
        </div>
      </div>

      <Parcours parcours={d.parcours} />

      <div className="c-deux">
        <section className="c-bloc" aria-labelledby="faire-titre">
          <div className="c-bloc__tete">
            <h2 className="c-h2" id="faire-titre">À faire aujourd&apos;hui</h2>
            <span className="m-micro">{pluriel(d.a_faire.length, "élément", "éléments")}</span>
          </div>
          {d.a_faire.length ? (
            <ul className="c-faire">
              {d.a_faire.map((i) => (
                <li key={`${i.type}-${i.cible.genre}-${i.cible.id}`}>
                  <span className={`c-pastille${i.ton ? " c-pastille--" + i.ton : ""}`}><Icone nom={i.pastille} /></span>
                  <div><p className="c-quoi">{i.titre}</p><p className="c-qui">{i.sous_titre}</p></div>
                  <Link className="c-btn c-btn--s" href={lienCible(i.cible)}>{i.bouton}</Link>
                </li>
              ))}
            </ul>
          ) : <p className="c-faire--vide">Rien à faire pour l&apos;instant.</p>}
        </section>
        <div className="c-pile">
          <section className="c-relances" aria-labelledby="rel-titre">
            <h2 className="c-h2" id="rel-titre">Relances automatiques</h2>
            <dl>
              <div><dt>Partent aujourd&apos;hui</dt><dd>{r.partent_aujourdhui}</dd></div>
              <div><dt>En cours</dt><dd>{r.en_cours}</dd></div>
              <div><dt>En pause</dt><dd>{r.en_pause}</dd></div>
              <div><dt>En échec</dt><dd className="c-alerte">{r.en_echec}</dd></div>
            </dl>
            {coque ? <p>Envoi {texteCreneau(coque.creneau)}.</p> : null}
          </section>
          <section className="c-bloc" aria-labelledby="ins-titre">
            <div className="c-bloc__tete">
              <h2 className="c-h2" id="ins-titre">Arrivés par la landing</h2>
              <Link className="c-lien-petit" href="/contacts?source=landing">Tout voir</Link>
            </div>
            {d.arrives_landing.length ? (
              <ul className="c-recents">
                {d.arrives_landing.map((x) => (
                  <li key={`${x.cible.genre}-${x.cible.id}`}>
                    <span className={`c-initiales${classeInitiales(x.type)}`}>{initiales(x.nom_affiche)}</span>
                    <Link href={lienCible(x.cible)} style={{ textDecoration: "none" }}>
                      <b>{x.nom_affiche}</b>
                      <span>{provenance(x)}{x.source_detail ? `, via ${majuscule(x.source_detail)}` : ""}</span>
                    </Link>
                    <time dateTime={x.cree_at}>{depuis(x.cree_at)}</time>
                  </li>
                ))}
              </ul>
            ) : <p className="c-recents--vide">Personne n&apos;est encore arrivé par la landing.</p>}
          </section>
        </div>
      </div>
    </>
  );
}
