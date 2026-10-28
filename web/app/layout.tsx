import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/crm.css";

export const metadata: Metadata = { title: "CRM MERCI" };

export default function Racine({ children }: { children: ReactNode }) {
  return (
    <html lang="fr">
      <body className="m-base">{children}</body>
    </html>
  );
}
