import "server-only";

/**
 * Protection CSRF : en plus du cookie SameSite=Lax, toute requête modifiant l'état doit
 * provenir de la même origine (en-tête Origin, ou à défaut Referer).
 */
export function isSameOrigin(request: Request): boolean {
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  if (!host) return false;
  const allowed = new Set<string>([host]);
  const appUrl = process.env.NEXT_PUBLIC_APP_URL;
  if (appUrl) {
    try {
      allowed.add(new URL(appUrl).host);
    } catch {
      /* ignore */
    }
  }
  const origin = request.headers.get("origin") ?? request.headers.get("referer");
  if (!origin) return false;
  try {
    return allowed.has(new URL(origin).host);
  } catch {
    return false;
  }
}

export const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
