"use client";

// Bloc « Séquence » de la fiche : pas de la séquence du contact, interrupteur de pause
// individuelle, inscription manuelle quand aucune séquence ne tourne.
import { useState } from "react";
import type { Fiche, SequenceCle } from "@/lib/types";
import { EtatSequence } from "./EtatSequence";
import { Icone } from "./Icone";
import { Interrupteur } from "./Interrupteur";

const NOMS: Record<SequenceCle, string> = {
  "donateur-bienvenue": "Bienvenue donateur",
  "donateur-pilote": "Ouverture du pilote",
  "entreprise-entrante": "Entreprise entrante",
  "association-bienvenue": "Bienvenue association",
  "entreprise-prospection": "Prospection LinkedIn",
};

export function SequenceContact({ fiche, onPause, onInscrire }: {
  fiche: Fiche;
  onPause: (pause: boolean) => Promise<void>;
  onInscrire: (sequence: SequenceCle) => Promise<void>;
}) {
  const [choix, setChoix] = useState<SequenceCle | "">(fiche.sequences_possibles[0] ?? "");
  const [erreur, setErreur] = useState<string | null>(null);
  const seq = fiche.sequence;
  const enCours = seq && ["due", "active", "pause"].includes(seq.etat.etat);

  async function agir(action: () => Promise<void>) {
    setErreur(null);
    try {
      await action();
    } catch (e) {
      setErreur(e instanceof Error ? e.message : "Action impossible.");
    }
  }

  return (
    <section className="c-bloc c-bloc--creme" aria-labelledby="seq-titre">
      <div className="c-bloc__tete">
        <h2 className="c-h2" id="seq-titre">Séquence</h2>
        {enCours && fiche.contact ? (
          <Interrupteur actif={!fiche.contact.pause} aria="Séquence active pour ce contact" style={{ fontSize: 14 }}
            onChange={(actif) => agir(() => onPause(!actif))}>Active</Interrupteur>
        ) : null}
      </div>
      {erreur ? <p className="c-erreur" role="alert">{erreur}</p> : null}
      {seq ? (
        <>
          <p className="m-petit" style={{ marginBottom: 16 }}>
            <b style={{ color: "var(--m-encre)" }}>{seq.definition.nom}</b>. <EtatSequence s={seq.etat} />
          </p>
          <ol className="c-pas">
            {seq.definition.pas.map((p) => {
              const e = seq.etat;
              const fait = p.numero < e.pas || (p.numero === e.pas && (e.etat === "arret" || e.etat === "fini"));
              const coupe = (e.etat === "arret" || e.etat === "echec") && p.numero > e.pas;
              return (
                <li key={p.numero} className={`${fait ? "c-fait" : ""}${coupe ? " c-coupe" : ""}`.trim() || undefined}>
                  <span className="c-pas__rond">{fait ? <Icone nom="coche" /> : p.numero}</span>
                  <div>
                    <b>{p.titre}</b>
                    <span>{p.delai_libelle}, {p.canal === "email" ? "e-mail" : "LinkedIn"}{coupe ? ", annulé" : ""}</span>
                  </div>
                </li>
              );
            })}
          </ol>
          {seq.etat.etat === "arret" ? (
            <p className="c-arret">
              <b>Arrêtée automatiquement.</b>{" "}
              {seq.etat.raison === "réponse reçue" ? "Le contact a répondu, la suite est à vous." : `Raison : ${seq.etat.raison ?? "arrêt"}.`}
            </p>
          ) : null}
          {seq.etat.etat === "echec" ? (
            <p className="c-arret"><b>En échec.</b> {seq.etat.raison ? `Raison : ${seq.etat.raison}. ` : ""}La séquence est suspendue.</p>
          ) : null}
        </>
      ) : (
        <>
          <p className="m-petit">Aucune séquence en cours.</p>
          {fiche.genre === "contact" && fiche.sequences_possibles.length ? (
            <div style={{ display: "grid", gap: 10, marginTop: 16 }}>
              {fiche.sequences_possibles.length > 1 ? (
                <label className="c-champ">Séquence
                  <select value={choix} onChange={(e) => setChoix(e.target.value as SequenceCle)}>
                    {fiche.sequences_possibles.map((s) => <option key={s} value={s}>{NOMS[s]}</option>)}
                  </select>
                </label>
              ) : null}
              <button className="c-btn c-btn--s" type="button" style={{ justifySelf: "start" }} disabled={!choix}
                onClick={() => choix && agir(() => onInscrire(choix))}>
                <Icone nom="plus" />Inscrire à {NOMS[(choix || fiche.sequences_possibles[0])]}
              </button>
            </div>
          ) : (
            <p className="m-micro" style={{ marginTop: 10 }}>
              {fiche.genre === "organisation" ? "Aucun décideur trouvé : pas de séquence possible." : "Aucune séquence possible pour ce contact."}
            </p>
          )}
        </>
      )}
    </section>
  );
}
