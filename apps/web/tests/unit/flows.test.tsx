import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { StatusControl } from "@/features/applications/status-control";
import { LoginForm } from "@/features/auth/login-form";
import { OpportunityFilters } from "@/features/opportunities/filters";
import type { Application } from "@/lib/types";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));

afterEach(() => vi.restoreAllMocks());

const app: Application = {
  id: "app-1",
  opportunity: { id: "o1", type: "internship", title: "Stage data", organization: "ACME", official_url: "https://acme.example", deadline_at: null, deadline_status: "unknown", status: "open", required_documents: [], countries: [] },
  status: "preparing", deadline_at: null, submitted_at: null, submission_confirmed_at: null, notes: null, contact_name: null,
  contact_email: null, next_action: null, next_action_at: null, follow_up_at: null, response_notes: null, response_received_at: null,
  estimated_prep_hours: null, created_at: "", updated_at: "", urgency: null, eligibility: null, score: null, documents: [], open_tasks: 0,
};

/** Réponses de connexion successives ; la configuration publique (inscriptions) est servie à part. */
function mockLogin(...responses: Response[]) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    if (String(input).includes("auth/config")) return new Response(JSON.stringify({ registration_open: false }), { status: 200 });
    return responses.shift()!;
  });
}
const loginCalls = (spy: ReturnType<typeof mockLogin>) => spy.mock.calls.filter((c) => c[0] === "/api/auth/login");

describe("connexion", () => {
  it("valide les champs avant tout appel réseau", async () => {
    const spy = mockLogin();
    render(<LoginForm />);
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByText("Adresse e-mail invalide.")).toBeInTheDocument();
    expect(loginCalls(spy)).toHaveLength(0);
  });

  it("affiche l'erreur du serveur puis redirige en cas de succès", async () => {
    const spy = mockLogin(
      new Response(JSON.stringify({ error: { code: "invalid_credentials", message: "Identifiants invalides." } }), { status: 401 }),
      new Response(JSON.stringify({ user: {} }), { status: 200 }),
    );
    render(<LoginForm />);
    await userEvent.type(screen.getByLabelText(/Adresse e-mail/), "moi@example.com");
    await userEvent.type(screen.getByLabelText(/Mot de passe/), "mauvais");
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByText("Identifiants invalides.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
    expect(loginCalls(spy)).toHaveLength(2);
  });
});

describe("validation humaine avant « Envoyée »", () => {
  it("exige une confirmation explicite", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ...app, status: "submitted", submission_confirmed_at: "now" }), { status: 200 }),
    );
    const onChanged = vi.fn();
    render(<ToastProvider><StatusControl app={app} onChanged={onChanged} /></ToastProvider>);
    await userEvent.selectOptions(screen.getByLabelText("Statut"), "submitted");
    expect(spy).not.toHaveBeenCalled();
    const confirm = screen.getByRole("button", { name: "Confirmer" });
    expect(confirm).toBeDisabled();
    await userEvent.click(screen.getByLabelText(/J'ai moi-même envoyé/));
    await userEvent.click(confirm);
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    const body = JSON.parse((spy.mock.calls[0]![1] as RequestInit).body as string);
    expect(body).toEqual({ status: "submitted", confirm_submission: true });
  });

  it("change directement les statuts sans envoi externe", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ...app, status: "to_prepare" }), { status: 200 }));
    render(<ToastProvider><StatusControl app={app} onChanged={vi.fn()} /></ToastProvider>);
    await userEvent.selectOptions(screen.getByLabelText("Statut"), "to_prepare");
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    expect(JSON.parse((spy.mock.calls[0]![1] as RequestInit).body as string).confirm_submission).toBe(false);
  });
});

describe("filtres du catalogue", () => {
  it("remet la pagination à 1 quand un filtre change", async () => {
    const onChange = vi.fn();
    render(<OpportunityFilters value={{ page: "3", sort: "-score" }} facets={{ countries: ["FR"], fields: [], organizations: [], types: [] }} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: /Filtres/ }));
    await userEvent.selectOptions(screen.getByLabelText("Type"), "internship");
    expect(onChange).toHaveBeenLastCalledWith({ page: "1", sort: "-score", type: "internship" });
    await userEvent.selectOptions(screen.getByLabelText("Pays"), "FR");
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ country: "FR", page: "1" }));
  });
});
