"use client";

// Arrivée par le lien magique : le jeton part dans le corps JSON, l'API pose le cookie de session.
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

function Verifier() {
  const jeton = useSearchParams().get("jeton");
  const [erreur, setErreur] = useState<string | null>(jeton ? null : "Lien incomplet, demandez-en un nouveau.");
  const lance = useRef(false);

  useEffect(() => {
    // Le jeton est à usage unique : une seule vérification, même si l'effet est rejoué.
    if (!jeton || lance.current) return;
    lance.current = true;
    api.auth.verifier(jeton)
      .then(() => window.location.replace("/"))
      .catch((e: Error) => setErreur(e.message));
  }, [jeton]);

  return (
    <main className="c-connexion">
      <div className="c-connexion__carte">
        <img src="/assets/logo-noir.png" alt="MERCI" width={110} height={30} />
        <h1 className="c-titre">Espace équipe</h1>
        {erreur ? (
          <>
            <p className="c-erreur" role="alert">{erreur}</p>
            <Link className="c-btn c-btn--plein c-btn--l" href="/connexion">Recevoir un nouveau lien</Link>
          </>
        ) : <p className="c-sous" role="status">Connexion en cours…</p>}
      </div>
    </main>
  );
}

export default function Page() {
  return <Suspense fallback={null}><Verifier /></Suspense>;
}
