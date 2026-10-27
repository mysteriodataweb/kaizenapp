"use client";

import { t } from "@/i18n";
import type { ApiErrorBody } from "./types";

/** Erreur API normalisée (format backend : {error: {code, message, details}}). */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Json = Record<string, unknown> | unknown[];

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  json?: Json;
  body?: FormData;
  signal?: AbortSignal;
}

/**
 * Appel de l'API métier via la passerelle Next.js (/api/backend/*).
 * Le navigateur ne voit jamais le jeton de session (cookie httpOnly) ni l'URL interne du backend.
 */
export async function api<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.body) {
    body = opts.body;
  }
  let response: Response;
  try {
    response = await fetch(`/api/backend/${path.replace(/^\//, "")}`, {
      method: opts.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: opts.signal,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "network_error", t.common.networkError);
  }
  if (response.status === 401 && typeof window !== "undefined" && !path.startsWith("auth/password-reset")) {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    // Rechargement complet volontaire : purge l'état client après expiration de session.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign(`/login?next=${next}&expired=1`);
    throw new ApiError(401, "unauthorized", "Session expirée.");
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  const data: unknown = text ? safeJson(text) : null;
  if (!response.ok) {
    const err = (data as ApiErrorBody | null)?.error;
    throw new ApiError(response.status, err?.code ?? `http_${response.status}`, err?.message ?? t.common.error, err?.details);
  }
  return data as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Fetcher SWR. */
export const fetcher = <T,>(path: string) => api<T>(path);

/** Construit une query-string en omettant les valeurs vides. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "" || value === false) continue;
    search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (Array.isArray(err.details) && err.code === "weak_password") return `${err.message} ${err.details.join(" ")}`;
    if (Array.isArray(err.details) && err.code === "validation_error") {
      const first = err.details[0] as { msg?: string; loc?: string[] } | undefined;
      if (first?.msg) return `${err.message} ${first.loc?.slice(1).join(".") ?? ""} : ${first.msg}`;
    }
    return err.message;
  }
  return t.common.error;
}
