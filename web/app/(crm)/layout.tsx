import type { ReactNode } from "react";
import { Coque } from "@/components/Coque";

// La coque charge /auth/moi (401 : retour à la connexion) et /coque à chaque navigation.
export default function MiseEnPageCrm({ children }: { children: ReactNode }) {
  return <Coque>{children}</Coque>;
}
