import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { backendUrl, SESSION_COOKIE } from "@/lib/server/config";
import { isSameOrigin } from "@/lib/server/csrf";

export async function POST(request: Request) {
  if (!isSameOrigin(request)) {
    return NextResponse.json({ error: { code: "csrf", message: "Origine refusée.", details: null } }, { status: 403 });
  }
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (token) {
    await fetch(`${backendUrl()}/api/v1/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    }).catch(() => undefined);
  }
  const response = NextResponse.json({ message: "Déconnecté." });
  response.cookies.delete(SESSION_COOKIE);
  return response;
}
