"use client";

// Pipelines, porté de `vPipelines` : onglets par pipeline, recherche, colonnes en glisser-déposer.
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useCoque } from "@/components/Coque";
import { Icone } from "@/components/Icone";
import { Kanban } from "@/components/Kanban";
import { Segments } from "@/components/Segments";
import { Attente } from "@/components/Vide";
import { api } from "@/lib/api";
import type { PipelineCle, PipelineRep } from "@/lib/types";
import { useDonnees } from "@/lib/useDonnees";

const PIPELINES: { cle: PipelineCle; nom: string }[] = [
  { cle: "donateurs", nom: "Donateurs" }, { cle: "entreprises", nom: "Entreprises" }, { cle: "associations", nom: "Associations" },
];

function Pipelines() {
  const router = useRouter();
  const params = useSearchParams();
  const { rechargerCoque } = useCoque();
  const p = params.get("p");
  const cle: PipelineCle = PIPELINES.some((x) => x.cle === p) ? (p as PipelineCle) : "entreprises";
  const [q, setQ] = useState("");
  const { donnees: d, erreur, recharger } = useDonnees<PipelineRep>(`${cle}|${q}`, () => api.pipelines.voir(cle, q.trim() || undefined));
  const [erreurDepot, setErreurDepot] = useState<string | null>(null);

  async function deplacer(affaireId: number, etape: string) {
    setErreurDepot(null);
    try {
      await api.affaires.modifier(affaireId, { etape });
    } catch (e) {
      setErreurDepot(e instanceof Error ? e.message : "Étape non modifiée.");
      throw e;
    } finally {
      recharger();
      rechargerCoque();
    }
  }

  return (
    <>
      <div className="c-tete">
        <div><p className="c-sous">Glissez une carte pour changer d&apos;étape. La séquence en cours s&apos;arrête si l&apos;étape change à la main.</p></div>
        <div className="c-actions"><Link className="c-btn c-btn--plein" href="/contacts?action=ajouter"><Icone nom="plus" />Ajouter</Link></div>
      </div>
      <div className="c-outils">
        <Segments libelle="Pipeline" valeur={cle} onChoix={(k) => router.replace(`/pipelines?p=${k}`)}
          options={PIPELINES.map((x) => ({ cle: x.cle, libelle: <>{x.nom} <span className="c-compte">{d?.compte_par_pipeline[x.cle] ?? 0}</span></> }))} />
        <div className="c-droite">
          <span className="c-perdus">Perdus : {d?.perdus ?? 0}</span>
          <label className="c-recherche"><Icone nom="prospection" />
            <input type="search" placeholder="Chercher dans ce pipeline" aria-label="Chercher" value={q} onChange={(e) => setQ(e.target.value)} />
          </label>
        </div>
      </div>
      {erreurDepot ? <p className="c-erreur" role="alert">{erreurDepot}</p> : null}
      {d && d.pipeline.cle === cle ? <Kanban colonnes={d.colonnes} onDeplacer={deplacer} /> : <Attente erreur={erreur} />}
    </>
  );
}

export default function Page() {
  return <Suspense fallback={<Attente erreur={null} />}><Pipelines /></Suspense>;
}
