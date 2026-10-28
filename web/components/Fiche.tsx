"use client";

// Fiche d'un contact ou d'une organisation sans décideur, portée de `vFiche` de la preview :
// coordonnées et note, fil d'activité, séquence.
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { classeInitiales, dateLongue, initiales, libelleSource, majuscule } from "@/lib/format";
import type { Fiche as FicheT, TypeContact } from "@/lib/types";
import { useDonnees } from "@/lib/useDonnees";
import { useCoque } from "./Coque";
import { FilActivite } from "./FilActivite";
import { Icone } from "./Icone";
import { SequenceContact } from "./SequenceContact";
import { Attente } from "./Vide";

function nomAffiche(f: FicheT): string {
  const c = f.contact;
  const nom = c ? [c.prenom, c.nom].filter(Boolean).join(" ") : "";
  return nom || f.organisation?.nom || c?.email || "Sans nom";
}

function sousTitre(f: FicheT): string {
  const c = f.contact, o = f.organisation;
  if (!c) return "Aucun décideur trouvé";
  if (c.type === "donateur") return c.ville ? `Donateur, ${c.ville}` : "Donateur";
  if (c.type === "association") return o?.nom ?? "Association";
  return [c.poste, o?.nom].filter(Boolean).join(", ") || "Entreprise";
}

export function Fiche({ genre, id }: { genre: "contact" | "organisation"; id: number }) {
  const { definirFil, rechargerCoque } = useCoque();
  const charger = () => (genre === "contact" ? api.contacts.voir(id) : api.organisations.voir(id));
  const { donnees: f, erreur, recharger, setDonnees } = useDonnees<FicheT>(`${genre}-${id}`, charger);
  const [erreurAction, setErreurAction] = useState<string | null>(null);

  useEffect(() => {
    definirFil(f ? nomAffiche(f) : null);
    return () => definirFil(null);
  }, [f, definirFil]);

  if (!f) return <Attente erreur={erreur} />;

  const c = f.contact, o = f.organisation, a = f.affaire;
  const type: TypeContact = c?.type ?? o?.type ?? "entreprise";
  const nom = nomAffiche(f);

  async function changerEtape(etape: string) {
    if (!a) return;
    setErreurAction(null);
    try {
      await api.affaires.modifier(a.id, { etape });
    } catch (e) {
      setErreurAction(e instanceof Error ? e.message : "Étape non modifiée.");
    }
    recharger();
    rechargerCoque();
  }

  const ordre = a ? a.etapes_possibles.map((e) => e.cle) : [];
  const avantDemo = a && type === "entreprise" && ordre.indexOf(a.etape.cle) < ordre.indexOf("demo_planifiee") && a.etape.cle !== "perdu";

  return (
    <>
      <div className="c-fiche-tete">
        <span className={`c-initiales${classeInitiales(type)}`}>{initiales(nom)}</span>
        <div><h2 className="c-titre">{nom}</h2><p className="c-sous">{sousTitre(f)}</p></div>
        <div className="c-actions">
          {a ? (
            <label className="c-etiquette" style={{ gap: 8 }}>Étape
              <select aria-label="Étape" style={{ border: 0, background: "none", font: "inherit", fontWeight: 750 }}
                value={a.etape.cle} onChange={(e) => changerEtape(e.target.value)}>
                {a.etapes_possibles.map((e) => <option key={e.cle} value={e.cle}>{e.nom}</option>)}
              </select>
            </label>
          ) : null}
          {avantDemo ? (
            <button className="c-btn c-btn--plein" type="button" onClick={() => changerEtape("demo_planifiee")}>
              <Icone nom="calendrier" />Planifier la démo
            </button>
          ) : c?.email ? (
            <a className="c-btn c-btn--plein" href={`mailto:${c.email}`}><Icone nom="email" />Écrire</a>
          ) : null}
        </div>
      </div>
      {erreurAction ? <p className="c-erreur" role="alert">{erreurAction}</p> : null}
      <div className="c-trois">
        <section className="c-bloc" aria-label="Coordonnées">
          <dl className="c-infos">
            {o ? <div><dt>{o.type === "association" ? "Association" : "Entreprise"}</dt><dd>{o.nom}{o.effectif_libelle ? `, ${o.effectif_libelle}` : ""}</dd></div> : null}
            {c?.poste ? <div><dt>Poste</dt><dd>{c.poste}</dd></div> : null}
            {c ? <div><dt>E-mail</dt><dd>{c.email ? <a href={`mailto:${c.email}`}>{c.email}</a> : "Inconnu"}</dd></div> : null}
            {c?.telephone ? <div><dt>Téléphone</dt><dd><a href={`tel:${c.telephone}`}>{c.telephone}</a></dd></div> : null}
            {c?.linkedin_url ? <div><dt>LinkedIn</dt><dd><a href={c.linkedin_url} target="_blank" rel="noreferrer">Profil LinkedIn</a></dd></div> : null}
            {o?.naf_libelle ? <div><dt>Secteur</dt><dd>{o.naf_libelle}</dd></div> : null}
            <div><dt>Ville</dt><dd>{c?.ville ?? o?.ville ?? "Inconnue"}</dd></div>
            {c ? <div><dt>Source</dt><dd>{libelleSource(c.source)}{c.source_detail ? `, ${majuscule(c.source_detail)}` : ""}</dd></div> : null}
            {c ? (
              <div><dt>Consentement</dt><dd>
                {c.desinscrit_at ? `Désinscrit le ${dateLongue(c.desinscrit_at)}`
                  : c.consentement_at ? `Accepté le ${dateLongue(c.consentement_at)}` : "Aucun"}
              </dd></div>
            ) : null}
            {f.hubspot ? (
              <div><dt>HubSpot</dt><dd style={f.hubspot.etat === "erreur" ? { color: "#B3261E" } : undefined}>
                {f.hubspot.etat === "ok" ? "Synchronisé avec HubSpot"
                  : f.hubspot.etat === "erreur" ? `Erreur : ${f.hubspot.message ?? "envoi impossible"}`
                  : "En attente"}
              </dd></div>
            ) : null}
            {f.autres_contacts.length ? (
              <div><dt>Autres contacts</dt><dd>
                {f.autres_contacts.map((x, i) => (
                  <span key={x.id}>{i ? ", " : ""}<Link href={`/contacts/${x.id}`}>{x.nom_affiche}</Link>{x.poste ? ` (${x.poste})` : ""}</span>
                ))}
              </dd></div>
            ) : null}
          </dl>
          {o?.note != null ? (
            <>
              <div className="c-separe" />
              <div className="c-bloc__tete" style={{ margin: 0 }}><h2 className="c-h3">Note de prospection</h2></div>
              <div className="c-note-grande"><strong>{o.note}</strong><span>/10</span></div>
              <ul className="c-raisons">{o.raisons.map((r) => <li key={r}>{r}</li>)}</ul>
            </>
          ) : null}
        </section>
        <FilActivite activites={f.activites} suivant={f.activites_suivant}
          onAjouter={async (texte) => {
            if (genre === "contact") await api.contacts.noter(id, { type: "note", texte });
            else await api.organisations.noter(id, { type: "note", texte });
            recharger();
          }}
          onPlus={async () => {
            if (f.activites_suivant === null) return;
            const suite = genre === "contact" ? await api.contacts.activites(id, f.activites_suivant) : await api.organisations.activites(id, f.activites_suivant);
            setDonnees({ ...f, activites: [...f.activites, ...suite.activites], activites_suivant: suite.suivant });
          }} />
        <SequenceContact key={`${f.sequence?.etat.inscription_id ?? "aucune"}-${f.sequences_possibles.join()}`} fiche={f}
          onPause={async (pause) => { await api.contacts.pause(id, pause); recharger(); rechargerCoque(); }}
          onInscrire={async (sequence) => { await api.contacts.inscrire(id, sequence); recharger(); rechargerCoque(); }} />
      </div>
    </>
  );
}
