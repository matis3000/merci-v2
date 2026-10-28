"use client";

// Bloc « HubSpot » de Réglages (lot L8, admin) : état de la synchro sens unique, compteurs,
// « Tout synchroniser », dernières erreurs, correspondance des étapes MERCI vers HubSpot.
import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";
import { depuis, pluriel } from "@/lib/format";
import type { HubspotEtapes, PipelineCle, PipelineDef, ReglagesCorps } from "@/lib/types";
import { useDonnees } from "@/lib/useDonnees";

const lienPetit = { border: 0, background: "none", cursor: "pointer" } as const;
const alerte = { color: "#B3261E", borderColor: "#B3261E" } as const;
const OBJETS = { contact: "Contact", organisation: "Organisation", affaire: "Affaire" } as const;

interface Choix { pipelines: PipelineDef[]; etapes: { id: string; label: string }[] }

export function BlocHubspot({ correspondance, onModifier }: {
  correspondance: HubspotEtapes;
  onModifier: (corps: ReglagesCorps) => Promise<void>;
}) {
  const { donnees: h, erreur, recharger } = useDonnees("hubspot-etat", api.hubspot.etat);
  const [message, setMessage] = useState<{ texte: string; alerte?: boolean } | null>(null);
  const [choix, setChoix] = useState<Choix | null>(null);
  const [ouvert, setOuvert] = useState(false);

  async function agir(action: () => Promise<void>) {
    setMessage(null);
    try {
      await action();
    } catch (e) {
      setMessage({ texte: e instanceof Error ? e.message : "Action impossible.", alerte: true });
    }
  }

  const reliees = Object.values(correspondance).reduce((n, etapes) => n + Object.keys(etapes).length, 0);

  async function ouvrir() {
    if (ouvert) { setOuvert(false); return; }
    await agir(async () => {
      const [pipelines, { etapes }] = await Promise.all([api.pipelines.liste(), api.hubspot.etapes()]);
      setChoix({ pipelines, etapes });
      setOuvert(true);
    });
  }

  function enregistrer(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const corps = {} as HubspotEtapes;
    for (const p of choix?.pipelines ?? []) {
      corps[p.cle as PipelineCle] = {};
      for (const etape of [...p.etapes, p.etape_perdue]) {
        const id = String(f.get(`${p.cle}.${etape.cle}`) ?? "");
        if (id) corps[p.cle as PipelineCle][etape.cle] = id;
      }
    }
    agir(async () => {
      await onModifier({ hubspot_etapes: corps });
      setOuvert(false);
      setMessage({ texte: "Correspondance enregistrée : elle s'applique aux prochains envois." });
    });
  }

  if (!h) {
    return (
      <section className="c-bloc" aria-labelledby="r-hubspot">
        <h2 className="c-h2" id="r-hubspot">HubSpot</h2>
        <p className="m-micro">{erreur ?? "Chargement…"}</p>
      </section>
    );
  }

  const c = h.compteurs;
  return (
    <section className="c-bloc" aria-labelledby="r-hubspot">
      <h2 className="c-h2" id="r-hubspot">HubSpot</h2>
      {message ? <p className={message.alerte ? "c-erreur" : "c-info"} role={message.alerte ? "alert" : "status"}>{message.texte}</p> : null}
      <div className="c-option">
        <div>
          <b>Copie vers HubSpot</b>
          <span>{h.etat === "non_connecte"
            ? "Jeton HUBSPOT_TOKEN absent : rien n'est envoyé, les modifications attendent le jeton."
            : "Contacts, organisations et affaires sont copiés vers HubSpot à chaque création ou modification."}</span>
        </div>
        {h.etat === "connecte" ? <span className="c-ok">Connecté</span>
          : h.etat === "erreurs" ? <span className="c-etiquette" style={alerte}>Erreurs</span>
          : <span className="c-etiquette">Non connecté</span>}
      </div>
      <div className="c-option">
        <div>
          <b>Objets</b>
          <span>
            {pluriel(c.synchronises, "synchronisé", "synchronisés")}, {c.en_attente} en attente, {c.en_erreur} en erreur
            {h.derniere_synchro_at ? `. Dernier envoi ${depuis(h.derniere_synchro_at)}` : ""}.
          </span>
        </div>
        <button className="c-btn c-btn--s" type="button" onClick={() => {
          if (!window.confirm("Tout synchroniser ? Chaque contact, organisation et affaire sera renvoyé vers HubSpot.")) return;
          agir(async () => {
            const rep = await api.hubspot.toutSynchroniser();
            setMessage({ texte: `${pluriel(rep.marques, "objet marqué", "objets marqués")} : l'envoi est lancé.` });
            recharger();
          });
        }}>Tout synchroniser</button>
      </div>
      <div className="c-option">
        <div>
          <b>Étapes des affaires</b>
          <span>{reliees
            ? `${pluriel(reliees, "étape reliée", "étapes reliées")} à une étape du pipeline HubSpot par défaut.`
            : "Aucune étape reliée : les affaires restent à la première étape du pipeline HubSpot, l'étape MERCI est copiée dans la propriété « Étape MERCI »."}</span>
        </div>
        {h.etat !== "non_connecte"
          ? <button className="c-lien-petit" type="button" style={lienPetit} onClick={ouvrir}>{ouvert ? "Fermer" : "Modifier"}</button>
          : null}
      </div>
      {ouvert && choix ? (
        <form onSubmit={enregistrer}>
          {choix.pipelines.map((p) => (
            <div key={p.cle}>
              <h3 className="c-h3" style={{ marginTop: 12 }}>{p.nom}</h3>
              <div className="c-champs">
                {[...p.etapes, p.etape_perdue].map((etape) => (
                  <label className="c-champ" key={etape.cle}>{etape.nom}
                    <select name={`${p.cle}.${etape.cle}`} defaultValue={correspondance[p.cle as PipelineCle]?.[etape.cle] ?? ""}>
                      <option value="">Non reliée</option>
                      {choix.etapes.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                    </select>
                  </label>
                ))}
              </div>
            </div>
          ))}
          <div className="c-actions">
            <button className="c-btn c-btn--s c-btn--plein" type="submit">Enregistrer</button>
            <button className="c-btn c-btn--s" type="button" onClick={() => setOuvert(false)}>Annuler</button>
          </div>
        </form>
      ) : null}
      {h.dernieres_erreurs.length ? (
        <>
          <div className="c-separe" />
          <h3 className="c-h3">Dernières erreurs</h3>
          {h.dernieres_erreurs.map((e) => (
            <div className="c-option" key={`${e.objet_type}-${e.objet_id}`}>
              <div>
                <b>{OBJETS[e.objet_type]} : {e.nom}</b>
                <span>{e.message}{e.nouvel_essai_at ? ", nouvel essai automatique" : ", plus de nouvel essai avant une modification"}.</span>
              </div>
              <span className="m-micro">{depuis(e.at)}</span>
            </div>
          ))}
        </>
      ) : null}
    </section>
  );
}
