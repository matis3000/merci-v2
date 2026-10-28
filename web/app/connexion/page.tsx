"use client";

// Connexion par lien magique, portée de `vConnexion`.
import { useState, type FormEvent } from "react";
import { api } from "@/lib/api";

export default function Connexion() {
  const [email, setEmail] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const [envoye, setEnvoye] = useState(false);
  const [devLien, setDevLien] = useState<string | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);

  async function demander(e: FormEvent) {
    e.preventDefault();
    setEnvoi(true);
    setErreur(null);
    try {
      const rep = await api.auth.lien(email.trim());
      setEnvoye(true);
      setDevLien(rep.dev_lien ?? null);
    } catch (err) {
      setErreur(err instanceof Error ? err.message : "Envoi impossible, réessayez.");
    } finally {
      setEnvoi(false);
    }
  }

  return (
    <main className="c-connexion">
      <div className="c-connexion__carte">
        <img src="/assets/logo-noir.png" alt="MERCI" width={110} height={30} />
        <h1 className="c-titre">Espace équipe</h1>
        <p className="c-sous">Recevez un lien de connexion par e-mail.</p>
        <form onSubmit={demander}>
          <label htmlFor="mail">E-mail de l&apos;équipe</label>
          <input id="mail" type="email" autoComplete="email" placeholder="prenom@merci.fr" required value={email}
            onChange={(e) => setEmail(e.target.value)} />
          <button className="c-btn c-btn--plein c-btn--l" type="submit" disabled={envoi}>Recevoir le lien</button>
        </form>
        {erreur ? <p className="c-erreur" role="alert">{erreur}</p> : null}
        {envoye ? (
          <p className="c-info" role="status">
            Si cette adresse fait partie de l&apos;équipe, un lien de connexion vient de partir. Ouvrez-le depuis ce navigateur.
            {devLien ? <> <a href={devLien}>Ouvrir le lien de développement</a></> : null}
          </p>
        ) : null}
        <p className="m-micro">Réservé à l&apos;équipe MERCI. Le lien est valable 15 minutes.</p>
      </div>
    </main>
  );
}
