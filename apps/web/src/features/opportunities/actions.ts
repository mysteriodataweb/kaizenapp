"use client";

import { api } from "@/lib/api";
import type { Application } from "@/lib/types";

export function setFavorite(id: string, favorite: boolean) {
  return api<{ is_favorite: boolean }>(`opportunities/${id}/favorite`, { method: favorite ? "POST" : "DELETE" });
}

export function trackOpportunity(id: string) {
  return api<Application>("applications", { method: "POST", json: { opportunity_id: id } });
}
