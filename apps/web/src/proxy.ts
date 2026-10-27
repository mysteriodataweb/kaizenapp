import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const SESSION_COOKIE = "oi_session";
const PUBLIC_PAGES = ["/login", "/forgot-password", "/reset-password"];

/**
 * Redirection rapide des visiteurs sans cookie. La vérification réelle de la session a lieu
 * côté serveur (layout privé -> /auth/me) et côté API pour chaque requête.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);
  const isPublic = PUBLIC_PAGES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  if (!hasSession && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname + request.nextUrl.search)}`;
    return NextResponse.redirect(url);
  }
  if (pathname === "/login" && request.nextUrl.searchParams.has("expired")) {
    // Session refusée par l'API : on efface le cookie périmé (évite une boucle de redirection).
    const response = NextResponse.next();
    response.cookies.delete(SESSION_COOKIE);
    return response;
  }
  if (hasSession && pathname === "/login") {
    return NextResponse.redirect(new URL("/dashboard", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|icon.svg|robots.txt).*)"],
};
