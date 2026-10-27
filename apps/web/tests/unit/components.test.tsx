import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "@/components/ui/button";
import { Field, Input } from "@/components/ui/form";
import { ScoreMeter } from "@/components/ui/progress";
import { Segmented } from "@/components/ui/segmented";
import { TagInput } from "@/components/ui/tag-input";
import { DeadlineBadge, EligibilityBadge, StatusBadge, UrgencyBadge } from "@/features/shared/badges";

describe("design system", () => {
  it("désactive un bouton en chargement", () => {
    render(<Button loading>Enregistrer</Button>);
    const btn = screen.getByRole("button", { name: "Enregistrer" });
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute("aria-busy", "true");
  });

  it("relie libellé, aide et erreur au champ", () => {
    render(<Field label="E-mail" hint="Votre adresse" error="Adresse invalide">{(p) => <Input {...p} />}</Field>);
    const input = screen.getByLabelText("E-mail");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input.getAttribute("aria-describedby")).toBeTruthy();
    expect(screen.getByRole("alert")).toHaveTextContent("Adresse invalide");
  });

  it("affiche les statuts en français", () => {
    render(<><StatusBadge status="submitted" /><StatusBadge status="to_explore" /><EligibilityBadge value="unknown" /></>);
    expect(screen.getByText("Envoyée")).toBeInTheDocument();
    expect(screen.getByText("À explorer")).toBeInTheDocument();
    expect(screen.getByText("À confirmer")).toBeInTheDocument();
  });

  it("distingue date inconnue et date non vérifiée", () => {
    render(<><DeadlineBadge at={null} status="unknown" /><DeadlineBadge at={new Date(Date.now() + 5 * 864e5).toISOString()} status="unverified" tz="UTC" /></>);
    expect(screen.getByText("Date inconnue")).toBeInTheDocument();
    expect(screen.getByText(/non vérifiée/)).toBeInTheDocument();
  });

  it("explique l'urgence aux lecteurs d'écran", () => {
    render(<UrgencyBadge urgency={{ level: "critique", score: 80, reasons: ["Échéance dans 2 jour(s).", "1 document manquant."], days_left: 2 }} />);
    expect(screen.getByText(/Urgence Critique/)).toBeInTheDocument();
    expect(screen.getByText(/Échéance dans 2 jour/)).toHaveClass("sr-only");
  });

  it("signale un score peu fiable", () => {
    render(<ScoreMeter score={82} confidence={0.3} />);
    expect(screen.getByText("82")).toBeInTheDocument();
    expect(screen.getByText("fiabilité faible")).toBeInTheDocument();
  });

  it("sélecteur de vue accessible (radiogroup)", async () => {
    const onChange = vi.fn();
    render(<Segmented label="Vue" value="a" onChange={onChange} options={[{ value: "a", label: "Kanban" }, { value: "b", label: "Tableau" }]} />);
    expect(screen.getByRole("radio", { name: "Kanban" })).toHaveAttribute("aria-checked", "true");
    await userEvent.click(screen.getByRole("radio", { name: "Tableau" }));
    expect(onChange).toHaveBeenCalledWith("b");
  });

  it("saisie de liste : ajout, normalisation et retrait", async () => {
    function Harness() {
      const [value, setValue] = useState<string[]>([]);
      return <TagInput label="Pays" value={value} onChange={setValue} normalize={(v) => (/^[a-z]{2}$/i.test(v) ? v.toUpperCase() : null)} />;
    }
    render(<Harness />);
    const input = screen.getByLabelText("Pays");
    await userEvent.type(input, "fr{enter}");
    expect(screen.getByText("FR")).toBeInTheDocument();
    await userEvent.type(input, "France{enter}");
    expect(screen.getByRole("alert")).toHaveTextContent("n'est pas une valeur valide");
    await userEvent.click(screen.getByRole("button", { name: "Retirer FR" }));
    expect(screen.queryByText("FR")).not.toBeInTheDocument();
  });
});
