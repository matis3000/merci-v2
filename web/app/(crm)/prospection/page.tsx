"use client";

// Prospection, porté de `vProspection` : cible, dernier passage, entreprises trouvées.
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { Icone } from "@/components/Icone";
import { Note } from "@/components/Note";
import { Attente } from "@/components/Vide";
import { api } from "@/lib/api";
import { depuis } from "@/lib/format";
import type { CibleProspection, ProspectionRep } from "@/lib/types";
import { useDonnees } from "@/lib/useDonnees";

const DEPARTEMENTS: Record<string, string> = { "67": "Bas-Rhin", "68": "Haut-Rhin", "57": "Moselle", "54": "Meurthe-et-Moselle", "88": "Vosges" };
const zone = (codes: string[]) => codes.map((c) => (DEPARTEMENTS[c] ? `${DEPARTEMENTS[c]} (${c})` : `Département ${c}`)).join(", ");
const liste = (v: FormDataEntryValue | null) => String(v ?? "").split(",").map((x) => x.trim()).filter(Boolean);
const VIDE = "Aucun passage pour l'instant. Le premier aura lieu demain à 6 h, ou lancez-le maintenant.";

function FormulaireCible({ cible, onFini }: { cible: CibleProspection; onFini: (enregistre: boolean) => void }) {
  const [erreur, setErreur] = useState<string | null>(null);

  async function envoyer(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setErreur(null);
    try {
      await api.prospection.cible({
        departements: liste(f.get("departements")),
        effectif_min: Number(f.get("effectif_min")),
        postes: liste(f.get("postes")),
        plafond_jour: Number(f.get("plafond_jour")),
        seuil: Number(f.get("seuil")),
      });
      onFini(true);
    } catch (err) {
      setErreur(err instanceof Error ? err.message : "Cible non enregistrée.");
    }
  }

  return (
    <form onSubmit={envoyer}>
      {erreur ? <p className="c-erreur" role="alert">{erreur}</p> : null}
      <div className="c-champs">
        <label className="c-champ">Départements (codes, séparés par des virgules)<input name="departements" defaultValue={cible.departements.join(", ")} required /></label>
        <label className="c-champ">Taille minimale
          <select name="effectif_min" defaultValue={cible.effectif_min}>
            {[50, 100, 200, 250, 500].map((n) => <option key={n} value={n}>{n} salariés et plus</option>)}
          </select>
        </label>
        <label className="c-champ">Invitations par jour<input name="plafond_jour" type="number" min={1} max={80} defaultValue={cible.plafond_jour} required /></label>
        <label className="c-champ">Note minimale (sur 10)<input name="seuil" type="number" min={1} max={10} defaultValue={cible.seuil} required /></label>
        <label className="c-champ c-champ--large">Postes visés (séparés par des virgules)<input name="postes" defaultValue={cible.postes.join(", ")} required /></label>
      </div>
      <div className="c-actions">
        <button className="c-btn c-btn--s c-btn--plein" type="submit">Enregistrer</button>
        <button className="c-btn c-btn--s" type="button" onClick={() => onFini(false)}>Annuler</button>
      </div>
    </form>
  );
}

export default function Prospection() {
  const { donnees: p, erreur, recharger } = useDonnees<ProspectionRep>("prospection", api.prospection.voir);
  const [edition, setEdition] = useState(false);
  const [erreurLancer, setErreurLancer] = useState<string | null>(null);

  // Un passage tourne en tâche de fond : on suit son avancement.
  const enCours = p?.en_cours ?? false;
  useEffect(() => {
    if (!enCours) return;
    const minuterie = setInterval(recharger, 4000);
    return () => clearInterval(minuterie);
  }, [enCours, recharger]);

  if (!p) return <Attente erreur={erreur} />;
  const d = p.dernier_passage;

  async function lancer() {
    setErreurLancer(null);
    try {
      await api.prospection.lancer();
    } catch (e) {
      setErreurLancer(e instanceof Error ? e.message : "Passage non lancé.");
    }
    recharger();
  }

  return (
    <>
      <div className="c-tete">
        <div>
          <p className="c-sous">
            Chaque matin à 6 h : le registre des entreprises, puis LinkedIn pour trouver les RH et RSE. Les prospects notés {p.cible.seuil}/10 ou plus entrent dans la séquence.
          </p>
        </div>
        <div className="c-actions">
          <button className="c-btn c-btn--plein" type="button" onClick={lancer} disabled={p.en_cours}>
            <Icone nom="prospection" />{p.en_cours ? "Passage en cours" : "Lancer maintenant"}
          </button>
        </div>
      </div>
      {erreurLancer ? <p className="c-erreur" role="alert">{erreurLancer}</p> : null}
      {d?.statut === "erreur" ? <p className="c-erreur" role="alert">Le dernier passage a échoué{d.erreur ? ` : ${d.erreur}` : "."}</p> : null}
      <div className="c-cible">
        <section className="c-bloc" aria-labelledby="cible-titre">
          <div className="c-bloc__tete">
            <h2 className="c-h2" id="cible-titre">Cible</h2>
            {!edition ? <button className="c-lien-petit" type="button" style={{ border: 0, background: "none", cursor: "pointer" }} onClick={() => setEdition(true)}>Modifier</button> : null}
          </div>
          {edition ? (
            <FormulaireCible cible={p.cible} onFini={(ok) => { setEdition(false); if (ok) recharger(); }} />
          ) : (
            <>
              <dl>
                <div><dt>Zone</dt><dd>{zone(p.cible.departements)}</dd></div>
                <div><dt>Taille</dt><dd>{p.cible.effectif_min} salariés et plus</dd></div>
                <div><dt>Invitations par jour</dt><dd>{p.cible.plafond_jour} au plus</dd></div>
              </dl>
              <div className="c-postes" aria-label="Postes visés">{p.cible.postes.map((x) => <span key={x}>{x}</span>)}</div>
            </>
          )}
        </section>
        <section className="c-passage" aria-labelledby="pass-titre">
          <h2 className="c-h2" id="pass-titre">
            {p.en_cours ? "Passage en cours" : d ? `Dernier passage, ${depuis(d.debut_at)}` : "Dernier passage"}
          </h2>
          <dl>
            <div><dt>Entreprises vues</dt><dd>{d?.entreprises_vues ?? 0}</dd></div>
            <div><dt>Nouvelles</dt><dd>{d?.nouvelles ?? 0}</dd></div>
            <div><dt>Décideurs trouvés</dt><dd>{d?.decideurs ?? 0}</dd></div>
            <div><dt>Entrées en séquence</dt><dd>{d?.en_sequence ?? 0}</dd></div>
          </dl>
          <p className="m-micro" style={{ marginTop: 14 }}>
            Invitations envoyées aujourd&apos;hui : {p.invitations_aujourdhui} sur {p.cible.plafond_jour}. Entreprises dont les décideurs restent à chercher : {p.a_rechercher}.
          </p>
        </section>
      </div>
      <div className="c-liste" role="table" aria-label="Entreprises du dernier passage">
        <div className="c-ligne c-ligne--pros c-ligne--tete" role="row">
          <span>Entreprise</span><span>Secteur</span><span>Salariés</span><span>Décideur</span><span>Note</span><span>Suite</span>
        </div>
        {p.entreprises.length ? p.entreprises.map((e) => (
          <div key={e.organisation_id} className="c-ligne c-ligne--pros" role="row">
            <span className="c-cell">
              <Link href={e.decideur ? `/contacts/${e.decideur.contact_id}` : `/organisations/${e.organisation_id}`} style={{ textDecoration: "none" }}>
                <b style={{ fontWeight: 700 }}>{e.nom}</b>
              </Link>
              {e.ville ? <small>{e.ville}</small> : null}
            </span>
            <span className="c-cell c-cell--muet">{e.naf_libelle ?? "Inconnu"}</span>
            <span className="c-cell">{e.effectif_libelle ?? "Inconnu"}</span>
            <span className="c-cell">
              {e.decideur ? `${e.decideur.nom}${e.decideur.poste ? `, ${e.decideur.poste}` : ""}` : <span className="c-cell--muet">Aucun trouvé</span>}
            </span>
            <span className="c-cell"><Note n={e.note} /></span>
            <span className="c-cell c-cell--muet">{e.suite_libelle}</span>
          </div>
        )) : <p className="c-ligne--vide">{d ? "Aucune entreprise retenue lors du dernier passage." : VIDE}</p>}
      </div>
    </>
  );
}
