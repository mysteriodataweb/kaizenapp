import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { backendUrl, SESSION_COOKIE } from "@/lib/server/config";
import { isSameOrigin, SAFE_METHODS } from "@/lib/server/csrf";

/** Routes accessibles sans session (réinitialisation du mot de passe). */
const PUBLIC_PATHS = new Set(["auth/password-reset/request", "auth/password-reset/confirm", "health"]);
/** Routes jamais relayées : la connexion passe par /api/auth/login pour ne pas exposer le jeton. */
const BLOCKED_PATHS = new Set(["auth/login"]);

function jsonError(status: number, code: string, message: string) {
  return NextResponse.json({ error: { code, message, details: null } }, { status });
}

async function handle(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (path.some((segment) => segment === ".." || segment.includes("/"))) return jsonError(400, "bad_path", "Chemin invalide.");
  const joined = path.join("/");
  if (BLOCKED_PATHS.has(joined)) return jsonError(404, "not_found", "Introuvable.");
  if (!SAFE_METHODS.has(request.method) && !isSameOrigin(request)) {
    return jsonError(403, "csrf", "Origine de la requête refusée.");
  }
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token && !PUBLIC_PATHS.has(joined)) return jsonError(401, "unauthorized", "Authentification requise.");

  const url = new URL(request.url);
  const target = `${backendUrl()}/api/v1/${joined}${url.search}`;
  const headers = new Headers();
  for (const name of ["content-type", "accept", "user-agent"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const ip = request.headers.get("x-forwarded-for")?.split(",")[0]?.trim();
  if (ip) headers.set("X-OI-Client-IP", ip);

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: SAFE_METHODS.has(request.method) ? undefined : await request.arrayBuffer(),
      cache: "no-store",
      redirect: "manual",
    });
  } catch {
    return jsonError(502, "backend_unreachable", "API injoignable. Réessayez dans un instant.");
  }
  const responseHeaders = new Headers();
  for (const name of ["content-type", "content-disposition", "cache-control", "x-request-id"]) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  responseHeaders.set("X-Content-Type-Options", "nosniff");
  if (upstream.status === 401) {
    const response = new NextResponse(upstream.body, { status: 401, headers: responseHeaders });
    if (token) response.cookies.delete(SESSION_COOKIE);
    return response;
  }
  return new NextResponse(upstream.status === 204 ? null : upstream.body, { status: upstream.status, headers: responseHeaders });
}

export { handle as DELETE, handle as GET, handle as PATCH, handle as POST, handle as PUT };
