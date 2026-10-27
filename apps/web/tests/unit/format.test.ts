import { describe, expect, it } from "vitest";

import { daysUntil, isoToLocalInput, localInputToIso, placeLabel, relativeDeadline } from "@/lib/format";

describe("dates dans le fuseau de l'utilisateur", () => {
  const now = new Date("2026-10-27T22:30:00Z"); // 23h30 à Paris, déjà le 28 à Tokyo

  it("compte les jours calendaires selon le fuseau", () => {
    const deadline = "2026-10-29T10:00:00Z";
    expect(daysUntil(deadline, "Europe/Paris", now)).toBe(2);
    expect(daysUntil(deadline, "Asia/Tokyo", now)).toBe(1);
  });

  it("signale une date inconnue ou non vérifiée au lieu de l'inventer", () => {
    expect(relativeDeadline(null, "unknown", "Europe/Paris", now)).toBe("Date limite inconnue");
    expect(relativeDeadline("2026-11-03T12:00:00Z", "unverified", "Europe/Paris", now)).toBe("J-7 (non vérifiée)");
    expect(relativeDeadline("2026-10-20T12:00:00Z", "confirmed", "Europe/Paris", now)).toMatch(/^Expirée depuis 7 j/);
    expect(relativeDeadline("2026-10-28T12:00:00Z", "confirmed", "Europe/Paris", now)).toBe("Demain");
  });

  it("convertit les champs datetime-local en ISO et inversement", () => {
    const iso = localInputToIso("2026-11-02T09:15");
    expect(iso).not.toBeNull();
    expect(isoToLocalInput(iso)).toBe("2026-11-02T09:15");
    expect(localInputToIso("")).toBeNull();
  });
});

describe("lieux", () => {
  it("évite les doublons ville/pays", () => {
    expect(placeLabel("Paris, France", ["FR"])).toBe("Paris, France");
    expect(placeLabel(null, ["DE", "FR"])).toBe("Allemagne · France");
  });
});
