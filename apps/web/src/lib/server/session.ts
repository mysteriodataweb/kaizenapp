import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import type { User } from "@/lib/types";
import { backendUrl, SESSION_COOKIE } from "./config";

export async function getSessionToken(): Promise<string | null> {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? null;
}

/** Vérifie la session côté serveur auprès de l'API (jamais sur la seule présence du cookie). */
export async function getCurrentUser(): Promise<User | null> {
  const token = await getSessionToken();
  if (!token) return null;
  try {
    const res = await fetch(`${backendUrl()}/api/v1/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    if (!res.ok) return null;
    return (await res.json()) as User;
  } catch {
    return null;
  }
}

export async function requireUser(): Promise<User> {
  const user = await getCurrentUser();
  if (!user) redirect("/login?expired=1");
  return user;
}
