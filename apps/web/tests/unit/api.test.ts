import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, errorMessage, qs } from "@/lib/api";

afterEach(() => vi.restoreAllMocks());

describe("client API", () => {
  it("passe par la passerelle et ne transmet jamais de jeton côté navigateur", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    await api("profile", { method: "PUT", json: { full_name: "A" } });
    const [url, init] = spy.mock.calls[0]!;
    expect(url).toBe("/api/backend/profile");
    expect((init as RequestInit).headers).not.toHaveProperty("Authorization");
    expect((init as RequestInit).credentials).toBe("same-origin");
  });

  it("normalise les erreurs du backend", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: { code: "application_exists", message: "Déjà suivie.", details: { application_id: "x" } } }), { status: 409 }),
    );
    const err = await api("applications", { method: "POST", json: {} }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("application_exists");
    expect(errorMessage(err)).toBe("Déjà suivie.");
  });

  it("signale une erreur réseau compréhensible", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const err = await api("dashboard").catch((e: unknown) => e);
    expect((err as ApiError).code).toBe("network_error");
  });

  it("construit des query strings sans valeurs vides", () => {
    expect(qs({ a: "1", b: "", c: null, d: false, e: 0, f: true })).toBe("?a=1&e=0&f=true");
    expect(qs({})).toBe("");
  });
});
