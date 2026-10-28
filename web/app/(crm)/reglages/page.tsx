"use client";

// Réglages, porté de `vReglages` : relances, connexions, équipe.
// La clé de l'App MERCI n'est affichée que masquée (décision D15).
import { useState, type FormEvent, type ReactNode } from "react";
import { BlocHubspot } from "@/components/BlocHubspot";
import { useCoque } from "@/components/Coque";
import { Icone } from "@/components/Icone";
import { Interrupteur } from "@/components/Interrupteur";
import { Attente } from "@/components/Vide";
import { api } from "@/lib/api";
import { dateLongue, depuis, majuscule, texteCreneau } from "@/lib/format";
import type { ReglagesCorps, ReglagesRep } from "@/lib/types";
import { useDonnees } from "@/lib/useDonnees";

type Edition = null | "creneau" | "expediteur" | "liens" | "inviter";
const JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];
const lienPetit = { border: 0, background: "none", cursor: "pointer" } as const;

const Ok = ({ children }: { children: ReactNode }) => <span className="c-ok">{children}</span>;
const Etiquette = ({ children, alerte }: { children: ReactNode; alerte?: boolean }) =>
  <span className="c-etiquette" style={alerte ? { color: "#B3261E", borderColor: "#B3261E" } : undefined}>{children}</span>;

const texte = (f: FormData, cle: string) => String(f.get(cle) ?? "").trim();

export default function Reglages() {
  const { moi, basculerPause, rechargerCoque } = useCoque();
  const { donnees: r, erreur, recharger, setDonnees } = useDonnees<ReglagesRep>("reglages", api.reglages.voir);
  const [edition, setEdition] = useState<Edition>(null);
  const [erreurAction, setErreurAction] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  if (!r) return <Attente erreur={erreur} />;
  const admin = moi.role === "admin";

  async function agir(action: () => Promise<void>) {
    setErreurAction(null);
    setInfo(null);
    try {
      await action();
      setEdition(null);
    } catch (e) {
      setErreurAction(e instanceof Error ? e.message : "Action impossible.");
    }
  }

  const modifier = (corps: ReglagesCorps) => agir(async () => { setDonnees(await api.reglages.modifier(corps)); rechargerCoque(); });

  function formulaire(e: FormEvent<HTMLFormElement>, lire: (f: FormData) => ReglagesCorps) {
    e.preventDefault();
    modifier(lire(new FormData(e.currentTarget)));
  }

  const boutonModifier = (cle: Edition) => admin || cle === "liens"
    ? <button className="c-lien-petit" type="button" style={lienPetit} onClick={() => setEdition(edition === cle ? null : cle)}>{edition === cle ? "Fermer" : "Modifier"}</button>
    : null;

  const actionsForm = (
    <div className="c-actions">
      <button className="c-btn c-btn--s c-btn--plein" type="submit">Enregistrer</button>
      <button className="c-btn c-btn--s" type="button" onClick={() => setEdition(null)}>Annuler</button>
    </div>
  );

  const cx = r.connexions;
  const fournisseurLinkedin = { connectsafely: "ConnectSafely", factice: "Fournisseur factice (développement)" }[cx.linkedin.fournisseur];

  return (
    <>
      <div className="c-tete">
        <div>
          <p className="c-sous">
            Pilote en Alsace, {r.pilote_ouvert_at ? `ouvert le ${dateLongue(r.pilote_ouvert_at)}` : "pas encore ouvert"}.
          </p>
        </div>
        <div className="c-actions">
          <button className="c-btn" type="button" onClick={async () => { await api.auth.deconnexion(); window.location.assign("/connexion"); }}>
            Se déconnecter
          </button>
        </div>
      </div>
      {erreurAction ? <p className="c-erreur" role="alert">{erreurAction}</p> : null}
      {info ? <p className="c-info" role="status">{info}</p> : null}
      <div className="c-reglages">
        <section className="c-bloc" aria-labelledby="r1">
          <h2 className="c-h2" id="r1">Relances</h2>
          <div className="c-option">
            <div><b>Relances automatiques</b><span>Coupe tout d&apos;un coup. Les séquences reprennent là où elles étaient.</span></div>
            <Interrupteur actif={!r.relances_en_pause} aria="Relances automatiques"
              onChange={(actif) => agir(async () => { await basculerPause(!actif); recharger(); })} />
          </div>
          <div className="c-option">
            <div><b>Créneau d&apos;envoi</b><span>{majuscule(texteCreneau(r.creneau))}, heure de Paris</span></div>
            {boutonModifier("creneau")}
          </div>
          {edition === "creneau" ? (
            <form onSubmit={(e) => formulaire(e, (f) => ({
              creneau: { jours: f.getAll("jours").map(Number), debut: Number(f.get("debut")), fin: Number(f.get("fin")) },
            }))}>
              <div className="c-jours">
                {JOURS.map((j, i) => (
                  <label key={j}><input type="checkbox" name="jours" value={i + 1} defaultChecked={r.creneau.jours.includes(i + 1)} />{j}</label>
                ))}
              </div>
              <div className="c-champs">
                <label className="c-champ">Début (heure)<input name="debut" type="number" min={0} max={23} defaultValue={r.creneau.debut} required /></label>
                <label className="c-champ">Fin (heure)<input name="fin" type="number" min={1} max={24} defaultValue={r.creneau.fin} required /></label>
              </div>
              {actionsForm}
            </form>
          ) : null}
          <div className="c-option">
            <div><b>Ouverture du pilote</b><span>Déclenche la séquence « Ouverture du pilote » pour tous les donateurs inscrits</span></div>
            {r.pilote_ouvert_at ? <Ok>Ouvert le {dateLongue(r.pilote_ouvert_at)}</Ok> : admin ? (
              <button className="c-btn c-btn--s" type="button" onClick={() => {
                if (!window.confirm("Ouvrir le pilote ? Tous les donateurs inscrits recevront la séquence « Ouverture du pilote ».")) return;
                agir(async () => {
                  const rep = await api.pilote.ouvrir();
                  setInfo(`Pilote ouvert : ${rep.inscrits} donateurs inscrits à la séquence.`);
                  recharger();
                  rechargerCoque();
                });
              }}>Ouvrir le pilote</button>
            ) : <Etiquette>Pas encore ouvert</Etiquette>}
          </div>
          <div className="c-option">
            <div><b>Expéditeur</b><span>{r.expediteur.nom}, {r.expediteur.email}{r.reponse_a ? `. Réponses à ${r.reponse_a}` : ""}</span></div>
            {boutonModifier("expediteur")}
          </div>
          {edition === "expediteur" ? (
            <form onSubmit={(e) => formulaire(e, (f) => ({
              expediteur: { nom: texte(f, "nom"), email: texte(f, "email") }, reponse_a: texte(f, "reponse_a") || null,
            }))}>
              <div className="c-champs">
                <label className="c-champ">Nom affiché<input name="nom" defaultValue={r.expediteur.nom} maxLength={80} required /></label>
                <label className="c-champ">Adresse d&apos;envoi<input name="email" type="email" defaultValue={r.expediteur.email} required /></label>
                <label className="c-champ">Adresse de réponse<input name="reponse_a" type="email" defaultValue={r.reponse_a ?? ""} /></label>
              </div>
              {actionsForm}
            </form>
          ) : null}
          <div className="c-option">
            <div>
              <b>Liens des messages</b>
              <span>Rendez-vous : {r.lien_rdv ?? "non renseigné"}. Création de compte : {r.lien_creation_compte ?? "non renseigné"}.</span>
            </div>
            {boutonModifier("liens")}
          </div>
          {edition === "liens" ? (
            <form onSubmit={(e) => formulaire(e, (f) => ({
              lien_rdv: texte(f, "lien_rdv") || null, lien_creation_compte: texte(f, "lien_creation_compte") || null,
            }))}>
              <div className="c-champs">
                <label className="c-champ">Lien de rendez-vous ({"{lien_rdv}"})<input name="lien_rdv" type="url" defaultValue={r.lien_rdv ?? ""} /></label>
                <label className="c-champ">Lien de création de compte ({"{lien_compte}"})<input name="lien_creation_compte" type="url" defaultValue={r.lien_creation_compte ?? ""} /></label>
              </div>
              {actionsForm}
            </form>
          ) : null}
          <p className="m-micro" style={{ marginTop: 12 }}>
            Les réponses par e-mail ne sont pas captées : quand un contact répond par e-mail, changez son étape à la main pour arrêter ses relances.
          </p>
        </section>

        <section className="c-bloc" aria-labelledby="r2">
          <h2 className="c-h2" id="r2">Connexions</h2>
          <div className="c-option">
            <div>
              <b>Formulaire de la landing</b>
              <span>{cx.landing.origines.length ? cx.landing.origines.join(", ") : "Aucune origine autorisée"}</span>
            </div>
            {cx.landing.derniere_inscription_at ? <Ok>Reçoit, dernière {depuis(cx.landing.derniere_inscription_at)}</Ok> : <Etiquette>Aucune inscription</Etiquette>}
          </div>
          <div className="c-option">
            <div>
              <b>E-mails, {cx.email.fournisseur === "resend" ? "Resend" : "boîte locale"}</b>
              <span>{cx.email.fournisseur === "resend" ? "Envoi par Resend" : "Clé Resend absente : les e-mails sont écrits dans le dossier outbox"}</span>
            </div>
            {cx.email.etat === "ok" ? <Ok>Connecté</Ok>
              : cx.email.etat === "erreur" ? <Etiquette alerte>En erreur{cx.email.derniere_erreur_at ? `, ${depuis(cx.email.derniere_erreur_at)}` : ""}</Etiquette>
              : <Etiquette>Non configuré</Etiquette>}
          </div>
          <div className="c-option">
            <div><b>LinkedIn</b><span>{fournisseurLinkedin}</span></div>
            {cx.linkedin.etat === "ok" ? <Ok>Connecté</Ok>
              : cx.linkedin.etat === "a_reconnecter" ? <Etiquette alerte>À reconnecter</Etiquette>
              : cx.linkedin.etat === "inconnu" ? <Etiquette>État inconnu</Etiquette>
              : <Etiquette>Non configuré</Etiquette>}
          </div>
          <div className="c-option">
            <div><b>App MERCI</b><span>Comptes créés et dons remontent tout seuls</span></div>
            {cx.app_merci.cle_configuree ? <Etiquette>Clé {cx.app_merci.cle_masquee}</Etiquette> : <Etiquette>Non configuré</Etiquette>}
          </div>
        </section>

        {admin ? (
          <BlocHubspot correspondance={r.hubspot_etapes}
            onModifier={async (corps) => { setDonnees(await api.reglages.modifier(corps)); }} />
        ) : null}

        <section className="c-bloc" aria-labelledby="r3">
          <div className="c-bloc__tete">
            <h2 className="c-h2" id="r3">Équipe</h2>
            {admin ? <button className="c-btn c-btn--s c-btn--plein" type="button" onClick={() => setEdition(edition === "inviter" ? null : "inviter")}><Icone nom="plus" />Inviter</button> : null}
          </div>
          {edition === "inviter" ? (
            <form onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              agir(async () => {
                await api.equipe.ajouter({ email: texte(f, "email"), prenom: texte(f, "prenom"), role: texte(f, "role") === "admin" ? "admin" : "equipe" });
                setInfo("Invitation envoyée : un lien de connexion est parti par e-mail.");
                recharger();
              });
            }}>
              <div className="c-champs">
                <label className="c-champ">Prénom<input name="prenom" maxLength={80} required /></label>
                <label className="c-champ">E-mail<input name="email" type="email" required /></label>
                <label className="c-champ">Rôle<select name="role" defaultValue="equipe"><option value="equipe">Équipe</option><option value="admin">Admin</option></select></label>
              </div>
              {actionsForm}
            </form>
          ) : null}
          {r.equipe.map((m) => (
            <div className="c-option" key={m.id}>
              <div><b>{m.prenom}</b><span>{m.email}{m.actif ? "" : ", désactivé"}</span></div>
              <div className="c-actions">
                {admin && m.id !== moi.id ? (
                  <button className="c-btn c-btn--s" type="button" onClick={() => agir(async () => { await api.equipe.modifier(m.id, { actif: !m.actif }); recharger(); })}>
                    {m.actif ? "Désactiver" : "Réactiver"}
                  </button>
                ) : null}
                <span className="c-etiquette">{m.role === "admin" ? "Admin" : "Équipe"}</span>
              </div>
            </div>
          ))}
        </section>
      </div>
    </>
  );
}
