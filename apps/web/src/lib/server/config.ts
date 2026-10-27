import "server-only";

/** URL interne du backend (Render). Jamais exposée au navigateur. */
export function backendUrl(): string {
  const url = process.env.BACKEND_API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  return url.replace(/\/$/, "");
}

export const SESSION_COOKIE = "oi_session";
export const isProduction = process.env.NODE_ENV === "production";
