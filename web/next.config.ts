import type { NextConfig } from "next";

// Le navigateur n'appelle que /api/* sur l'origine du web (décision D1) : le cookie de session posé
// par l'API appartient ainsi au domaine du web, ni cookie tiers ni CORS.
// En local, Next relaie /api/* vers l'API (API_URL). Sur Vercel (services, vercel.json à la racine),
// /api/* est routé avant Next vers le service `api`, qui monte ses routes sous /api : pas de relais ici.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8010";

const config: NextConfig = {
  async rewrites() {
    if (process.env.VERCEL) return [];
    return [{ source: "/api/:chemin*", destination: `${API_URL}/:chemin*` }];
  },
};

export default config;
