import { type Dictionary, fr } from "./fr";

export const locales = ["fr"] as const;
export type Locale = (typeof locales)[number];

const dictionaries: Record<Locale, Dictionary> = { fr };

/** Langue active. Unique pour l'instant ; prête pour un sélecteur fr/en. */
export const locale: Locale = "fr";
export const t: Dictionary = dictionaries[locale];

/** Libellé d'une valeur d'énumération avec repli lisible. */
export function label(group: Record<string, string>, value: string | null | undefined): string {
  if (!value) return t.common.none;
  return group[value] ?? value;
}
