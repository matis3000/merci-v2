"use client";

import { useParams } from "next/navigation";
import { Fiche } from "@/components/Fiche";

export default function FicheContact() {
  const { id } = useParams<{ id: string }>();
  return <Fiche genre="contact" id={Number(id)} />;
}
