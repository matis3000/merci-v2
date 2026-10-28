// Formats d'affichage : dates en Europe/Paris, noms, libellés.
import type { Creneau, EtatSequence, Iso, Jour, PipelineCle, Source, TypeContact } from "./types";

const FUSEAU = "Europe/Paris";
const JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];

export const majuscule = (s: string) => (s ? s[0].toUpperCase() + s.slice(1) : s);

/** "2026-10-12" vers "Lundi 12 octobre". */
export function jourLong(jour: Jour): string {
  const [a, m, j] = jour.split("-").map(Number);
  const d = new Date(Date.UTC(a, m - 1, j, 12));
  return majuscule(new Intl.DateTimeFormat("fr-FR", { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" }).format(d));
}

function parties(iso: Iso) {
  const p = new Intl.DateTimeFormat("fr-FR", {
    timeZone: FUSEAU, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(iso));
  const v = (t: string) => p.find((x) => x.type === t)?.value ?? "";
  return { jour: `${v("year")}-${v("month")}-${v("day")}`, h: Number(v("hour")), min: Number(v("minute")) };
}

const jourParis = (d: Date) => parties(d.toISOString()).jour;
const ecartJours = (a: Jour, b: Jour) => Math.round((Date.parse(a + "T00:00:00Z") - Date.parse(b + "T00:00:00Z")) / 86400000);

/** "9 h", "10 h 15". */
export function heure(iso: Iso): string {
  const { h, min } = parties(iso);
  return min ? `${h} h ${String(min).padStart(2, "0")}` : `${h} h`;
}

function dateCourte(iso: Iso): string {
  return new Intl.DateTimeFormat("fr-FR", { timeZone: FUSEAU, weekday: "long", day: "numeric", month: "short" }).format(new Date(iso));
}

/** Moment passé : "il y a 12 min", "il y a 2 h", "hier, 16 h 12", "mercredi 4 nov., 9 h 40". */
export function depuis(iso: Iso): string {
  const ms = Date.now() - Date.parse(iso);
  if (ms < 60_000) return "à l'instant";
  if (ms < 3_600_000) return `il y a ${Math.floor(ms / 60_000)} min`;
  const ecart = ecartJours(jourParis(new Date()), parties(iso).jour);
  if (ecart === 0) return `il y a ${Math.floor(ms / 3_600_000)} h`;
  if (ecart === 1) return `hier, ${heure(iso)}`;
  return `${dateCourte(iso)}, ${heure(iso)}`;
}

/** Moment à venir : "à 10 h 15", "demain 9 h", "jeudi", "le 24 oct.". */
export function bientot(iso: Iso): string {
  const ecart = ecartJours(parties(iso).jour, jourParis(new Date()));
  if (ecart <= 0) return `à ${heure(iso)}`;
  if (ecart === 1) return `demain ${heure(iso)}`;
  if (ecart < 7) return new Intl.DateTimeFormat("fr-FR", { timeZone: FUSEAU, weekday: "long" }).format(new Date(iso));
  return "le " + new Intl.DateTimeFormat("fr-FR", { timeZone: FUSEAU, day: "numeric", month: "short" }).format(new Date(iso));
}

/** "12 octobre 2026". */
export function dateLongue(iso: Iso): string {
  return new Intl.DateTimeFormat("fr-FR", { timeZone: FUSEAU, day: "numeric", month: "long", year: "numeric" }).format(new Date(iso));
}

/** Initiales à partir du nom affiché : "Prénom Nom" vers "PN", un seul mot vers ses deux premières lettres. */
export function initiales(nom: string): string {
  const mots = nom.trim().split(/\s+/).filter(Boolean);
  if (!mots.length) return "?";
  if (mots.length === 1) return mots[0].slice(0, 2).toUpperCase();
  return (mots[0][0] + mots[1][0]).toUpperCase();
}

export const classeInitiales = (type: TypeContact) =>
  type === "entreprise" ? " c-initiales--e" : type === "association" ? " c-initiales--a" : "";

export const classeNote = (n: number) => (n >= 9 ? "haut" : n >= 7 ? "bien" : n >= 6 ? "moyen" : "bas");

const SOURCES: Record<Source, string> = { landing: "Landing", prospection: "Prospection", import: "Import CSV", manuel: "Saisie manuelle" };
export const libelleSource = (s: Source) => SOURCES[s];

const PIPELINES: Record<PipelineCle, string> = { donateurs: "Donateurs", entreprises: "Entreprises", associations: "Associations" };
export const nomPipeline = (p: PipelineCle) => PIPELINES[p];

/** Complément de l'état de séquence : quand part le prochain pas, ou pourquoi il attend. */
function quand(s: EtatSequence): string {
  if (s.attente === "acceptation") return "attend l'acceptation";
  if (s.attente === "plafond") return "file d'attente du plafond";
  if (s.attente === "linkedin_deconnecte") return "LinkedIn à reconnecter";
  if (!s.prochain_envoi_at) return "en attente";
  if (Date.parse(s.prochain_envoi_at) <= Date.now()) return "au prochain créneau";
  return bientot(s.prochain_envoi_at);
}

/** Libellé d'état, comme la preview : "Part …", "Pas n/N, …", "En pause", "Échec : …", "Arrêtée : …", "Terminée". */
export function texteEtat(s: EtatSequence): string {
  switch (s.etat) {
    case "due": return `Part ${quand(s)}`;
    case "active": return `Pas ${s.pas}/${s.total}, ${quand(s)}`;
    case "pause": return "En pause";
    case "echec": return `Échec : ${s.raison ?? "envoi impossible"}`;
    case "arret": return `Arrêtée : ${s.raison ?? "arrêt manuel"}`;
    case "fini": return "Terminée";
  }
}

function plageJours(jours: number[]): string {
  const j = [...jours].sort((a, b) => a - b);
  const suite = j.every((x, i) => i === 0 || x === j[i - 1] + 1);
  if (j.length > 2 && suite) return `du ${JOURS[j[0] - 1]} au ${JOURS[j[j.length - 1] - 1]}`;
  const noms = j.map((x) => JOURS[x - 1]);
  return "le " + (noms.length > 1 ? noms.slice(0, -1).join(", ") + " et " + noms[noms.length - 1] : noms[0]);
}

/** "du lundi au vendredi, de 9 h à 18 h". */
export function texteCreneau(c: Creneau): string {
  return `${plageJours(c.jours)}, de ${c.debut} h à ${c.fin} h`;
}

/** Version courte du menu : "Lundi au vendredi, 9 h à 18 h." */
export function texteCreneauCourt(c: Creneau): string {
  return `${majuscule(plageJours(c.jours).replace(/^(du|le) /, ""))}, ${c.debut} h à ${c.fin} h.`;
}

export const pluriel = (n: number, un: string, plusieurs: string) => `${n} ${n > 1 ? plusieurs : un}`;
