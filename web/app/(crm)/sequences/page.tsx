"use client";

// Séquences, porté de `vSequences` : liste à gauche, détail, statistiques, textes modifiables.
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent, type ReactNode } from "react";
import { useCoque } from "@/components/Coque";
import { Icone } from "@/components/Icone";
import { Interrupteur } from "@/components/Interrupteur";
import { Attente } from "@/components/Vide";
import { api } from "@/lib/api";
import { pluriel, texteCreneau } from "@/lib/format";
import type { PasDef, SequenceCle, SequenceListe } from "@/lib/types";
import { useDonnees } from "@/lib/useDonnees";

// Variables {prenom} mises en avant comme dans la preview.
function texte(t: string): ReactNode[] {
  return t.split(/(\{[^}]+\})/g).map((morceau, i) =>
    /^\{[^}]+\}$/.test(morceau) ? <em key={i}>{morceau.slice(1, -1)}</em> : morceau);
}

function Pas({ cle, pas, onEnregistre }: { cle: SequenceCle; pas: PasDef; onEnregistre: () => void }) {
  const [edition, setEdition] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const email = pas.canal === "email";

  async function enregistrer(corps: { sujet?: string; corps: string }) {
    setErreur(null);
    try {
      await api.sequences.modifierPas(cle, pas.numero, corps);
      setEdition(false);
      onEnregistre();
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "Texte non enregistré.");
    }
  }

  function envoyer(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    enregistrer({ ...(email ? { sujet: String(f.get("sujet") ?? "") } : {}), corps: String(f.get("corps") ?? "") });
  }

  return (
    <li>
      <div className="c-quand">
        <b>{pas.delai_libelle}</b>
        <span className="c-canal"><Icone nom={email ? "email" : "linkedin"} />{email ? "E-mail" : "LinkedIn"}</span>
      </div>
      <div className="c-message">
        <b>{pas.titre}</b>
        {edition ? (
          <form onSubmit={envoyer}>
            {erreur ? <p className="c-erreur" role="alert" style={{ marginTop: 8 }}>{erreur}</p> : null}
            <div className="c-champs" style={{ gridTemplateColumns: "1fr", margin: "8px 0 0" }}>
              {email ? <label className="c-champ">Sujet<input name="sujet" defaultValue={pas.sujet ?? ""} maxLength={200} required /></label> : null}
              <label className="c-champ">Texte (variables : {"{prenom}"}, {"{entreprise}"}, {"{lien_rdv}"}, {"{lien_compte}"})
                <textarea name="corps" defaultValue={pas.corps} maxLength={5000} required />
              </label>
            </div>
            <div className="c-actions" style={{ marginTop: 8 }}>
              <button className="c-btn c-btn--s c-btn--plein" type="submit">Enregistrer</button>
              <button className="c-btn c-btn--s" type="button" onClick={() => setEdition(false)}>Annuler</button>
              {pas.personnalise ? <button className="c-btn c-btn--s" type="button" onClick={() => enregistrer({ corps: "" })}>Revenir au texte par défaut</button> : null}
            </div>
          </form>
        ) : (
          <>
            <p style={{ whiteSpace: "pre-line" }}>{texte(pas.corps)}</p>
            <button className="c-btn c-btn--s" type="button" onClick={() => setEdition(true)}>
              Modifier le texte{pas.personnalise ? " (personnalisé)" : ""}
            </button>
          </>
        )}
      </div>
    </li>
  );
}

function Sequences() {
  const params = useSearchParams();
  const { coque } = useCoque();
  const { donnees: liste, erreur, recharger } = useDonnees<SequenceListe[]>("sequences", api.sequences.liste);
  const [erreurCoupure, setErreurCoupure] = useState<string | null>(null);
  if (!liste) return <Attente erreur={erreur} />;

  const s = liste.find((x) => x.cle === params.get("s")) ?? liste.find((x) => x.cle === "entreprise-prospection") ?? liste[0];
  // Séquence qui commence par une invitation LinkedIn : on suit les acceptations, comme la preview.
  const sansOuverture = s.stats.ouverts === null || (s.pas[0]?.canal === "linkedin_invitation" && s.stats.acceptees !== null);

  async function couper(active: boolean) {
    setErreurCoupure(null);
    try {
      await api.sequences.couper(s.cle, !active);
      recharger();
    } catch (e) {
      setErreurCoupure(e instanceof Error ? e.message : "Réglage non enregistré.");
    }
  }

  return (
    <>
      <div className="c-tete">
        <div>
          <p className="c-sous">
            Elles partent seules{coque ? `, ${texteCreneau(coque.creneau)}` : ""}. Une réponse, une désinscription ou un changement d&apos;étape les arrête.
          </p>
        </div>
      </div>
      <div className="c-seq">
        <nav className="c-seq-liste" aria-label="Séquences">
          {liste.map((x) => (
            <Link key={x.cle} className="c-seq-item" href={`/sequences?s=${x.cle}`} aria-current={x.cle === s.cle ? "page" : undefined}>
              <b>{x.nom}</b>
              <span>{x.public}. {x.declencheur}</span>
              <span className={`c-etat c-etat--${x.actifs ? "active" : "arret"}`}>{pluriel(x.actifs, "contact en cours", "contacts en cours")}</span>
            </Link>
          ))}
        </nav>
        <section className="c-bloc" aria-labelledby="s-titre">
          <div className="c-bloc__tete">
            <div>
              <h2 className="c-h2" id="s-titre">{s.nom}</h2>
              <p className="m-petit" style={{ marginTop: 4 }}>Démarre : {s.declencheur.toLowerCase()}.</p>
            </div>
            <Interrupteur actif={!s.coupee} aria="Séquence active" style={{ fontSize: 15 }} onChange={couper}>Active</Interrupteur>
          </div>
          {erreurCoupure ? <p className="c-erreur" role="alert">{erreurCoupure}</p> : null}
          <dl className="c-chiffres">
            <div><dt>En cours</dt><dd>{s.actifs}</dd></div>
            <div><dt>Envoyés</dt><dd>{s.stats.envoyes}</dd></div>
            <div><dt>{sansOuverture ? "Acceptées" : "Ouverts"}</dt><dd>{sansOuverture ? s.stats.acceptees ?? 0 : s.stats.ouverts}</dd></div>
            <div><dt>Réponses</dt><dd>{s.stats.reponses}</dd></div>
          </dl>
          <ol className="c-etapes-seq">
            {s.pas.map((p) => <Pas key={`${s.cle}-${p.numero}-${p.corps.length}-${p.personnalise}`} cle={s.cle} pas={p} onEnregistre={recharger} />)}
          </ol>
          <p className="c-arret" style={{ marginTop: 20 }}>
            <b>S&apos;arrête seule si :</b> le contact répond, se désinscrit, l&apos;e-mail rebondit, ou l&apos;étape change à la main.
          </p>
        </section>
      </div>
    </>
  );
}

export default function Page() {
  return <Suspense fallback={<Attente erreur={null} />}><Sequences /></Suspense>;
}
