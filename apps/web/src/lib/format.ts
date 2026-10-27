/** Formatage des dates (stockées en UTC, affichées dans le fuseau de l'utilisateur), pays, langues. */

const LOCALE = "fr-FR";

export function formatDate(iso: string | null | undefined, tz?: string, withTime = false): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(LOCALE, {
    timeZone: tz,
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(date);
}

/** Clé AAAA-MM-JJ d'une date dans un fuseau donné. */
export function dayKey(date: Date, tz?: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
  return parts;
}

/** Jours calendaires restants dans le fuseau de l'utilisateur (négatif si dépassé). */
export function daysUntil(iso: string, tz?: string, now: Date = new Date()): number {
  const target = Date.parse(dayKey(new Date(iso), tz));
  const today = Date.parse(dayKey(now, tz));
  return Math.round((target - today) / 86_400_000);
}

export function relativeDeadline(iso: string | null, status: string, tz?: string, now: Date = new Date()): string {
  if (!iso || status === "unknown") return "Date limite inconnue";
  const days = daysUntil(iso, tz, now);
  const suffix = status === "unverified" ? " (non vérifiée)" : "";
  if (days < 0) return `Expirée depuis ${-days} j${suffix}`;
  if (days === 0) return `Aujourd'hui${suffix}`;
  if (days === 1) return `Demain${suffix}`;
  return `J-${days}${suffix}`;
}

const regionNames = typeof Intl.DisplayNames === "function" ? new Intl.DisplayNames([LOCALE], { type: "region" }) : null;
const languageNames = typeof Intl.DisplayNames === "function" ? new Intl.DisplayNames([LOCALE], { type: "language" }) : null;

export function countryName(code: string): string {
  try {
    return regionNames?.of(code.toUpperCase()) ?? code;
  } catch {
    return code;
  }
}

export function languageName(code: string): string {
  try {
    const name = languageNames?.of(code.toLowerCase()) ?? code;
    return name.charAt(0).toUpperCase() + name.slice(1);
  } catch {
    return code;
  }
}

/** Lieu lisible sans doublon (« Paris, France » + FR -> « Paris, France »). */
export function placeLabel(location: string | null, countries: string[], max = 3): string {
  const names = countries.map(countryName).filter((name) => !location?.toLowerCase().includes(name.toLowerCase()));
  return [location, ...names].filter(Boolean).slice(0, max).join(" · ");
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} o`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(0)} Ko`;
  return `${(size / 1024 / 1024).toFixed(1)} Mo`;
}

export function confidenceLabel(confidence: number): string {
  if (confidence >= 0.8) return "élevée";
  if (confidence >= 0.5) return "moyenne";
  return "faible";
}

/** Convertit une valeur <input type="datetime-local"> (heure locale du navigateur) en ISO UTC. */
export function localInputToIso(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export function isoToLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Liste des codes pays ISO usuels pour les sélecteurs (noms affichés via Intl). */
export const COMMON_COUNTRIES = [
  "FR", "DE", "BE", "NL", "LU", "CH", "AT", "ES", "PT", "IT", "IE", "GB", "SE", "NO", "DK", "FI", "PL", "CZ",
  "HU", "RO", "GR", "EE", "LT", "LV", "US", "CA", "MX", "BR", "AR", "IN", "CN", "JP", "KR", "SG", "AU", "NZ",
  "AE", "IL", "TR", "SN", "CI", "MA", "TN", "DZ", "EG", "NG", "GH", "KE", "ZA", "RW", "CM", "BJ", "TG", "BF",
  "ML", "NE", "GN", "MG", "CD", "CG", "GA", "MU",
];

export const COMMON_LANGUAGES = ["fr", "en", "de", "es", "it", "pt", "nl", "ar", "zh", "ja", "ru", "wo", "sw", "ko", "tr", "pl", "sv"];
export const CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2", "native"];
