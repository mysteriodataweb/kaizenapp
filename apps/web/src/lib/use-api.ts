"use client";

import useSWR, { type SWRConfiguration } from "swr";

import { fetcher } from "./api";

/** Lecture de l'API avec cache SWR. `path` à null = requête suspendue. */
export function useApi<T>(path: string | null, config?: SWRConfiguration<T>) {
  return useSWR<T>(path, fetcher<T>, { revalidateOnFocus: false, ...config });
}
