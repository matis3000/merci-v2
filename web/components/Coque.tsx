"use client";

// Coque de l'app, portée de la fonction `coque` de la preview : menu à gauche, zone principale
// en carte, barre de titre, bandeaux de pause générale et de LinkedIn à reconnecter.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import { jourLong, texteCreneauCourt } from "@/lib/format";
import type { CoqueRep, Membre } from "@/lib/types";
import { Icone, type NomIcone } from "./Icone";
import { Attente } from "./Vide";

interface ContexteCoque {
  coque: CoqueRep | null;
  moi: Membre;
  rechargerCoque: () => void;
  basculerPause: (enPause: boolean) => Promise<void>;
  definirFil: (nom: string | null) => void;
}

const Contexte = createContext<ContexteCoque | null>(null);

export function useCoque(): ContexteCoque {
  const c = useContext(Contexte);
  if (!c) throw new Error("useCoque hors de la coque");
  return c;
}

type Rubrique = "accueil" | "pipelines" | "contacts" | "sequences" | "prospection" | "reglages";
const TITRES: Record<Rubrique, string> = {
  accueil: "Accueil", pipelines: "Pipelines", contacts: "Contacts", sequences: "Séquences", prospection: "Prospection", reglages: "Réglages",
};

function rubrique(chemin: string): Rubrique {
  if (chemin.startsWith("/organisations")) return "contacts";
  const premier = chemin.split("/")[1] as Rubrique;
  return premier in TITRES ? premier : "accueil";
}

export function Coque({ children }: { children: ReactNode }) {
  const chemin = usePathname();
  const actif = rubrique(chemin);
  const estFiche = /^\/(contacts|organisations)\/\d+/.test(chemin);
  const [moi, setMoi] = useState<Membre | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [coque, setCoque] = useState<CoqueRep | null>(null);
  const [fil, definirFil] = useState<string | null>(null);

  useEffect(() => {
    api.auth.moi().then(setMoi).catch((e: Error) => setErreur(e.message));
  }, []);

  const rechargerCoque = useCallback(() => {
    api.coque().then(setCoque).catch(() => undefined);
  }, []);

  // Compteurs du menu et état des relances rafraîchis à chaque navigation.
  useEffect(() => { rechargerCoque(); }, [chemin, rechargerCoque]);

  const enPause = coque?.relances_en_pause ?? false;
  useEffect(() => {
    document.documentElement.classList.toggle("relances-off", enPause);
  }, [enPause]);

  const basculerPause = useCallback(async (pause: boolean) => {
    setCoque((c) => (c ? { ...c, relances_en_pause: pause } : c));
    try {
      await api.reglages.modifier({ relances_en_pause: pause });
    } finally {
      rechargerCoque();
    }
  }, [rechargerCoque]);

  useEffect(() => {
    const titre = estFiche ? "fiche contact" : TITRES[actif].toLowerCase();
    document.title = `CRM MERCI, ${titre}`;
  }, [actif, estFiche]);

  if (!moi) return <main className="c-connexion"><Attente erreur={erreur} /></main>;

  const lien = (cle: Rubrique, href: string, nb?: number) => (
    <Link href={href} aria-current={cle === actif ? "page" : undefined}>
      <Icone nom={cle as NomIcone} /><span>{TITRES[cle]}</span>{nb ? <span className="c-nb">{nb}</span> : null}
    </Link>
  );

  return (
    <Contexte.Provider value={{ coque, moi, rechargerCoque, basculerPause, definirFil }}>
      <a className="c-cache" href="#contenu">Aller au contenu</a>
      <div className="c-app">
        <aside className="c-side">
          <Link href="/" aria-label="MERCI, accueil du CRM">
            <img className="c-side__logo" src="/assets/logo-noir.png" alt="MERCI" width={80} height={22} />
          </Link>
          <nav className="c-nav" aria-label="Menu">
            {lien("accueil", "/")}
            {lien("pipelines", "/pipelines")}
            {lien("contacts", "/contacts", coque?.nb_contacts)}
            <div className="c-nav__sec">Automatisation</div>
            {lien("sequences", "/sequences", coque?.nb_sequences_en_cours)}
            {lien("prospection", "/prospection")}
            <div className="c-nav__sec">Compte</div>
            {lien("reglages", "/reglages")}
          </nav>
          <div className="c-side__relances">
            <label className="c-switch">
              <span>{enPause ? "Relances en pause" : "Relances actives"}</span>
              <input type="checkbox" checked={!enPause} disabled={!coque} aria-label="Relances automatiques"
                onChange={(e) => basculerPause(!e.target.checked)} />
            </label>
            {coque ? <p>{texteCreneauCourt(coque.creneau)}</p> : null}
          </div>
          <div className="c-moi">
            <span className="c-moi__av">{moi.prenom.slice(0, 1).toUpperCase()}</span>
            <div><b>{moi.prenom}</b><span>{moi.email}</span></div>
            <Link href="/reglages" aria-label="Réglages"><Icone nom="reglages" /></Link>
          </div>
        </aside>
        <div className="c-main">
          <header className="c-top">
            <h1>
              {estFiche ? (
                <><Icone nom="contacts" /><Link href="/contacts">Contacts</Link><i>/</i>{fil ?? ""}</>
              ) : (
                <><Icone nom={actif as NomIcone} />{TITRES[actif]}</>
              )}
            </h1>
            {coque ? <span className="c-top__date">{jourLong(coque.aujourdhui)}</span> : null}
          </header>
          <main className="c-corps" id="contenu">
            <div className="c-bandeau" role="status">
              <Icone nom="pause" />
              <span>Toutes les relances sont en pause. Rien ne part tant que vous ne les relancez pas.</span>
              <button className="c-btn c-btn--s" type="button" onClick={() => basculerPause(false)}>
                <Icone nom="lecture" />Reprendre
              </button>
            </div>
            {coque?.linkedin.etat === "a_reconnecter" ? (
              <div className="c-bandeau c-bandeau--alerte" role="alert">
                <Icone nom="attention" />
                <span>Le compte LinkedIn est à reconnecter. Les pas LinkedIn sont suspendus, les e-mails continuent.</span>
              </div>
            ) : null}
            {children}
          </main>
        </div>
      </div>
    </Contexte.Provider>
  );
}
