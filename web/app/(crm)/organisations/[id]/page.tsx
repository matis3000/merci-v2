"use client";

import { useParams } from "next/navigation";
import { Fiche } from "@/components/Fiche";

export default function FicheOrganisation() {
  const { id } = useParams<{ id: string }>();
  return <Fiche genre="organisation" id={Number(id)} />;
}
