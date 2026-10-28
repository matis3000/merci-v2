"use client";

// Contacts, porté de `vContacts` : filtres par type, recherche, import, export, ajout.
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useRef, useState, type FormEvent } from "react";
import { useCoque } from "@/components/Coque";
import { Icone } from "@/components/Icone";
import { ListeContacts } from "@/components/ListeContacts";
import { Segments } from "@/components/Segments";
import { Attente } from "@/components/Vide";
import { api } from "@/lib/api";
import { pluriel } from "@/lib/format";
import type { ContactsRep, FiltresContacts, ImportRep, NouveauContact, Source, TypeContact } from "@/lib/types";
import { useDonnees } from "@/lib/useDonnees";

type Filtre = "tous" | TypeContact;
const TYPES: { cle: Filtre; libelle: string }[] = [
  { cle: "tous", libelle: "Tous" }, { cle: "donateur", libelle: "Donateurs" },
  { cle: "entreprise", libelle: "Entreprises" }, { cle: "association", libelle: "Associations" },
];
const SOURCES: Source[] = ["landing", "prospection", "import", "manuel"];
const PAR_PAGE = 50;

function FormulaireAjout({ onFini }: { onFini: () => void }) {
  const router = useRouter();
  const [type, setType] = useState<TypeContact>("donateur");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  async function envoyer(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const champs = new FormData(e.currentTarget);
    const corps: NouveauContact = { type };
    for (const cle of ["prenom", "nom", "email", "telephone", "poste", "organisation_nom", "ville", "linkedin_url"] as const) {
      const v = String(champs.get(cle) ?? "").trim();
      if (v) corps[cle] = v;
    }
    setEnvoi(true);
    setErreur(null);
    try {
      const fiche = await api.contacts.creer(corps);
      onFini();
      router.push(fiche.genre === "contact" ? `/contacts/${fiche.id}` : `/organisations/${fiche.id}`);
    } catch (err) {
      setErreur(err instanceof Error ? err.message : "Contact non enregistré.");
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <form className="c-bloc c-panneau" onSubmit={envoyer} aria-labelledby="ajout-titre">
      <div className="c-bloc__tete"><h2 className="c-h2" id="ajout-titre">Ajouter un contact</h2>
        <button className="c-btn c-btn--s" type="button" onClick={onFini}>Annuler</button></div>
      {erreur ? <p className="c-erreur" role="alert">{erreur}</p> : null}
      <div className="c-champs">
        <label className="c-champ">Type
          <select value={type} onChange={(e) => setType(e.target.value as TypeContact)}>
            <option value="donateur">Donateur</option><option value="entreprise">Entreprise</option><option value="association">Association</option>
          </select>
        </label>
        <label className="c-champ">Prénom<input name="prenom" maxLength={80} /></label>
        <label className="c-champ">Nom<input name="nom" maxLength={80} /></label>
        <label className="c-champ">E-mail<input name="email" type="email" maxLength={254} /></label>
        <label className="c-champ">Téléphone<input name="telephone" type="tel" maxLength={40} /></label>
        {type !== "donateur" ? <label className="c-champ">{type === "association" ? "Association" : "Entreprise"}<input name="organisation_nom" maxLength={200} /></label> : null}
        {type === "entreprise" ? <label className="c-champ">Poste<input name="poste" maxLength={120} /></label> : null}
        {type === "entreprise" ? <label className="c-champ">Profil LinkedIn<input name="linkedin_url" type="url" maxLength={300} /></label> : null}
        <label className="c-champ">Ville<input name="ville" maxLength={120} /></label>
      </div>
      <button className="c-btn c-btn--plein" type="submit" disabled={envoi}>Enregistrer</button>
    </form>
  );
}

function Contacts() {
  const router = useRouter();
  const params = useSearchParams();
  const { rechargerCoque } = useCoque();
  const t = params.get("t");
  const filtre: Filtre = TYPES.some((x) => x.cle === t) ? (t as Filtre) : "tous";
  const s = params.get("source");
  const source = SOURCES.includes(s as Source) ? (s as Source) : undefined;
  const [q, setQ] = useState(params.get("q") ?? "");
  const [page, setPage] = useState(1);
  const [ajout, setAjout] = useState(params.get("action") === "ajouter");
  const [bilan, setBilan] = useState<ImportRep | null>(null);
  const [erreurImport, setErreurImport] = useState<string | null>(null);
  const fichier = useRef<HTMLInputElement>(null);

  const filtres: FiltresContacts = { type: filtre === "tous" ? undefined : filtre, source, q: q.trim() || undefined, page, par_page: PAR_PAGE };
  const { donnees: d, erreur, recharger } = useDonnees<ContactsRep>(JSON.stringify(filtres), () => api.contacts.liste(filtres));

  function choisir(cle: Filtre) {
    const u = new URLSearchParams(params.toString());
    if (cle === "tous") u.delete("t"); else u.set("t", cle);
    u.delete("action");
    setPage(1);
    router.replace(`/contacts${u.toString() ? "?" + u.toString() : ""}`);
  }

  async function importer(f: File | undefined) {
    if (!f) return;
    setBilan(null);
    setErreurImport(null);
    try {
      setBilan(await api.contacts.importer(f));
      recharger();
      rechargerCoque();
    } catch (e) {
      setErreurImport(e instanceof Error ? e.message : "Import impossible.");
    } finally {
      if (fichier.current) fichier.current.value = "";
    }
  }

  const exportFiltres = { ...filtres, page: undefined, par_page: undefined };
  const filtreActif = filtre !== "tous" || source || q.trim();

  return (
    <>
      <div className="c-tete">
        <div>
          <p className="c-sous">
            {d ? `${pluriel(d.total, "contact", "contacts")}, dont ${d.resume.landing} arrivés par la landing et ${d.resume.prospection} par la prospection.` : " "}
          </p>
        </div>
        <div className="c-actions">
          <input ref={fichier} type="file" accept=".csv,text/csv" hidden onChange={(e) => importer(e.target.files?.[0])} />
          <button className="c-btn" type="button" onClick={() => fichier.current?.click()}><Icone nom="import" />Importer un CSV</button>
          <a className="c-btn" href={api.contacts.lienExport(exportFiltres)} download><Icone nom="export" />Exporter</a>
          <button className="c-btn c-btn--plein" type="button" onClick={() => setAjout(true)}><Icone nom="plus" />Ajouter</button>
        </div>
      </div>
      {params.get("action") === "importer" && !bilan && !erreurImport ? (
        <p className="c-info">Choisissez un fichier CSV avec « Importer un CSV ». Colonnes lues : type, prenom, nom, email, telephone, poste, organisation, ville, linkedin_url, source, source_detail.</p>
      ) : null}
      {erreurImport ? <p className="c-erreur" role="alert">{erreurImport}</p> : null}
      {bilan ? (
        <p className="c-info" role="status">
          Import terminé : {bilan.crees} créés, {bilan.mis_a_jour} mis à jour, {bilan.ignores} ignorés.
          {bilan.erreurs.length ? ` Lignes refusées : ${bilan.erreurs.slice(0, 5).map((x) => `${x.ligne} (${x.raison})`).join(", ")}${bilan.erreurs.length > 5 ? "…" : ""}` : ""}
        </p>
      ) : null}
      {ajout ? <FormulaireAjout onFini={() => setAjout(false)} /> : null}
      <div className="c-outils">
        <Segments libelle="Type" valeur={filtre} onChoix={choisir} options={TYPES} />
        <div className="c-droite">
          <label className="c-recherche"><Icone nom="prospection" />
            <input type="search" placeholder="Nom, e-mail, entreprise" aria-label="Chercher un contact" value={q}
              onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          </label>
        </div>
      </div>
      {d ? (
        <>
          <ListeContacts lignes={d.lignes}
            vide={filtreActif ? "Aucun contact ne correspond." : "Aucun contact. Ils arriveront par la landing, la prospection ou un import CSV."} />
          {d.total > PAR_PAGE ? (
            <div className="c-outils" style={{ marginTop: 16 }}>
              <button className="c-btn c-btn--s" type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>Page précédente</button>
              <span className="m-micro">Page {d.page} sur {Math.ceil(d.total / d.par_page)}</span>
              <button className="c-btn c-btn--s" type="button" disabled={page * PAR_PAGE >= d.total} onClick={() => setPage(page + 1)}>Page suivante</button>
            </div>
          ) : null}
        </>
      ) : <Attente erreur={erreur} />}
    </>
  );
}

export default function Page() {
  return <Suspense fallback={<Attente erreur={null} />}><Contacts /></Suspense>;
}
