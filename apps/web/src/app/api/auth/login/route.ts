import { NextResponse } from "next/server";
import { z } from "zod";

import { backendUrl, isProduction, SESSION_COOKIE } from "@/lib/server/config";
import { isSameOrigin } from "@/lib/server/csrf";

const schema = z.object({ email: z.email(), password: z.string().min(1).max(256) });

export async function POST(request: Request) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: { code: "csrf", message: "Origine refusée.", details: null } }, { status: 403 });
  }
  const parsed = schema.safeParse(await request.json().catch(() => null));
  if (!parsed.success) {
    return NextResponse.json({ error: { code: "validation_error", message: "E-mail ou mot de passe invalide.", details: null } }, { status: 422 });
  }
  let res: Response;
  try {
    res = await fetch(`${backendUrl()}/api/v1/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "User-Agent": request.headers.get("user-agent") ?? "web",
        "X-OI-Client-IP": request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "",
      },
      body: JSON.stringify(parsed.data),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ error: { code: "backend_unreachable", message: "API injoignable.", details: null } }, { status: 502 });
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) return NextResponse.json(data, { status: res.status });
  // Le jeton reste dans un cookie httpOnly : jamais accessible au JavaScript du navigateur.
  const response = NextResponse.json({ user: data.user });
  response.cookies.set(SESSION_COOKIE, data.token, {
    httpOnly: true,
    secure: isProduction,
    sameSite: "lax",
    path: "/",
    expires: new Date(data.expires_at),
  });
  return response;
}
