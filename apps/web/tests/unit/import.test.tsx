import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { orderQueue, QueueView } from "@/features/applications/queue-view";
import { extractLinks, ImportView } from "@/features/opportunities/import-view";
import { type OfferValues, toOfferPayload } from "@/features/opportunities/offer-form";
import { UserProvider } from "@/features/shared/user-context";
import type { Application, ImportPreview, User } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/opportunities/new",
}));

afterEach(() => {
  vi.restoreAllMocks();
  push.mockReset();
});

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const user: User = { id: "u1", email: "moi@example.com", display_name: null, is_admin: false, timezone: "Europe/Paris", locale: "fr", last_seen_at: null, previous_seen_at: null };
const wrap = (ui: React.ReactNode) =>
  render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}><UserProvider user={user}><ToastProvider>{ui}</ToastProvider></UserProvider></SWRConfig>);

const LINKEDIN = "https://www.linkedin.com/jobs/view/4012345678";
const preview: ImportPreview = {
  url: LINKEDIN,
  existing_opportunity_id: null,
  fetched: false,
  method: "linkedin-url+texte",
  ai_used: true,
  notes: ["Texte analysé par l'IA : seules les informations présentes dans le texte sont reprises.", "À compléter : le type."],
  draft: {
    official_url: LINKEDIN, type: null, title: "Stagiaire Data Analyst", organization: "ACME", description: "Analyse de données.",
    location: "Paris", countries: ["FR"], remote: null, deadline_date: "2027-03-15", duration_months: 6, fields: [], stipend: null,
    required_documents: ["CV"], eligibility_criteria: null,
  },
};

describe("enregistrement rapide de plusieurs liens", () => {
  it("extrait les liens d'un texte collé, sans doublon", () => {
    expect(extractLinks(`${LINKEDIN}\n texte  ${LINKEDIN} https://x.example/a\nftp://nope`)).toEqual([LINKEDIN, "https://x.example/a"]);
  });

  it("enregistre les liens puis propose de commencer à postuler", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json({ items: [{ url: LINKEDIN, opportunity_id: "o1", application_id: "a1", created: true, title: "Offre LinkedIn n° 4012345678", error: null },
        { url: "https://x.example/a", opportunity_id: "o2", application_id: "a2", created: false, title: "Stage", error: null }],
      created: 1, already_saved: 1, errors: 0 }),
    );
    wrap(<ImportView />);
    await userEvent.type(screen.getByLabelText(/Liens des offres/), `${LINKEDIN}\nhttps://x.example/a`);
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer 2 liens" }));
    expect(await screen.findByText(/1 enregistrée\(s\) · 1 déjà présente\(s\) · 0 erreur\(s\)/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Commencer à postuler" })).toHaveAttribute("href", "/queue");
    const body = JSON.parse((spy.mock.calls[0]![1] as RequestInit).body as string);
    expect(body).toEqual({ urls: [LINKEDIN, "https://x.example/a"], type: "internship" });
  });
});

describe("offre détaillée avec texte collé", () => {
  async function openDetailed() {
    wrap(<ImportView />);
    await userEvent.click(screen.getByRole("radio", { name: "Une offre détaillée" }));
  }

  it("envoie le lien et le texte, pré-remplit le brouillon IA, exige le type puis enregistre", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).includes("import/preview") ? json(preview) : json({ opportunity_id: "opp-1", created: true, application_id: "app-1", message: "Offre enregistrée dans votre liste." }),
    );
    await openDetailed();
    await userEvent.type(screen.getByLabelText(/Adresse de la page/), LINKEDIN);
    expect(screen.getByText(/LinkedIn ne peut pas être lu automatiquement/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Texte de l'offre/), "Stagiaire Data Analyst chez ACME");
    await userEvent.click(screen.getByRole("button", { name: "Analyser" }));
    expect(await screen.findByText("Brouillon rempli par l'IA : relisez chaque champ")).toBeInTheDocument();
    const sent = JSON.parse((spy.mock.calls[0]![1] as RequestInit).body as string);
    expect(sent).toEqual({ url: LINKEDIN, text: "Stagiaire Data Analyst chez ACME" });
    expect(screen.getByLabelText(/^Intitulé/)).toHaveValue("Stagiaire Data Analyst");
    expect(screen.getByLabelText(/^Durée/)).toHaveValue("6");

    await userEvent.click(screen.getByRole("button", { name: "Enregistrer l'offre" }));
    expect(await screen.findByText("Choisissez le type.")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText(/^Type/), "internship");
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer l'offre" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/opportunities/opp-1"));
    const saved = JSON.parse((spy.mock.calls.find((c) => String(c[0]).endsWith("opportunities/import"))![1] as RequestInit).body as string);
    expect(saved).toMatchObject({ type: "internship", title: "Stagiaire Data Analyst", required_documents: ["CV"], duration_months: 6, follow: true });
  });

  it("renvoie vers l'offre déjà enregistrée", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ ...preview, existing_opportunity_id: "opp-9" }));
    await openDetailed();
    await userEvent.type(screen.getByLabelText(/Adresse de la page/), LINKEDIN);
    await userEvent.click(screen.getByRole("button", { name: "Analyser" }));
    expect(await screen.findByText("Cette offre est déjà enregistrée")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir l'offre" })).toHaveAttribute("href", "/opportunities/opp-9");
  });

  it("affiche le refus d'un lien non public", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ error: { code: "invalid_link", message: "Lien refusé : cette adresse ne correspond pas à un site public." } }, 422));
    await openDetailed();
    await userEvent.type(screen.getByLabelText(/Adresse de la page/), "http://127.0.0.1/admin");
    await userEvent.click(screen.getByRole("button", { name: "Analyser" }));
    expect(await screen.findByText(/ne correspond pas à un site public/)).toBeInTheDocument();
  });
});

describe("charge utile d'une offre", () => {
  it("convertit les champs vides en null et ne confirme jamais une date absente", () => {
    const v: OfferValues = {
      official_url: " https://x.example/o ", type: "masters_scholarship", title: " Bourse ", organization: " Univ ", location: "",
      countries: [], remote: "no", deadline_date: "", deadline_confirmed: true, duration_months: "24", funding_type: "full",
      funding_amount: "", stipend: "", study_levels: ["bachelor"], fields: [], required_documents: ["CV"],
      eligibility_criteria: "  ", description: "", follow: false,
    };
    expect(toOfferPayload(v)).toEqual({
      official_url: "https://x.example/o", type: "masters_scholarship", title: "Bourse", organization: "Univ", location: null,
      countries: [], remote: false, deadline_date: null, deadline_confirmed: false, duration_months: 24, funding_type: "full",
      funding_amount: null, stipend: null, study_levels: ["bachelor"], fields: [], required_documents: ["CV"],
      eligibility_criteria: null, description: null,
    });
  });
});

function app(id: string, extra: Partial<Application> & { title?: string; oppDeadline?: string | null } = {}): Application {
  const { title = `Offre ${id}`, oppDeadline = null, ...rest } = extra;
  return {
    id, status: "to_explore", deadline_at: null, submitted_at: null, submission_confirmed_at: null, notes: null, contact_name: null,
    contact_email: null, next_action: null, next_action_at: null, follow_up_at: null, response_notes: null, response_received_at: null,
    estimated_prep_hours: null, created_at: "2026-10-01T10:00:00Z", updated_at: "", urgency: null, eligibility: null, score: null,
    documents: [], open_tasks: 0,
    opportunity: { id: `o-${id}`, type: "internship", title, organization: "ACME", official_url: `https://www.linkedin.com/jobs/view/${id}`,
      deadline_at: oppDeadline, deadline_status: oppDeadline ? "unverified" : "unknown", status: "open", required_documents: [], countries: [] },
    ...rest,
  } as Application;
}

describe("liste « À postuler »", () => {
  const now = new Date("2026-11-01T00:00:00Z");

  it("ordonne : échéance proche, puis sans date (ordre d'ajout), puis dépassées ; ignore les envoyées", () => {
    const apps = [
      app("sans-date-2", { created_at: "2026-10-03T00:00:00Z" }),
      app("loin", { oppDeadline: "2027-01-01T00:00:00Z" }),
      app("depassee", { oppDeadline: "2026-10-15T00:00:00Z" }),
      app("proche", { deadline_at: "2026-11-10T00:00:00Z" }),
      app("sans-date-1", { created_at: "2026-10-02T00:00:00Z" }),
      app("envoyee", { status: "submitted" }),
    ];
    expect(orderQueue(apps, now).map((a) => a.id)).toEqual(["proche", "loin", "sans-date-1", "sans-date-2", "depassee"]);
  });

  it("montre une offre à la fois, « Plus tard » la repousse, « J'ai postulé » exige une confirmation", async () => {
    const apps = [app("1", { title: "Première", oppDeadline: "2030-01-01T00:00:00Z" }), app("2", { title: "Deuxième" }), app("3", { title: "Déjà envoyée", status: "submitted" })];
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) =>
      (init as RequestInit | undefined)?.method === "PATCH" ? json({ ...apps[0], status: "submitted" }) : json(apps),
    );
    wrap(<QueueView />);
    expect(await screen.findByRole("heading", { name: "Première" })).toBeInTheDocument();
    expect(screen.getByText("1 envoyée(s) sur 3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Ouvrir l'offre/ })).toHaveAttribute("href", "https://www.linkedin.com/jobs/view/1");

    await userEvent.click(screen.getByRole("button", { name: "Plus tard" }));
    expect(screen.getByRole("heading", { name: "Deuxième" })).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "J'ai postulé" }));
    const dialog = screen.getByRole("dialog", { name: "Candidature envoyée ?" });
    const confirm = within(dialog).getByRole("button", { name: "Confirmer" });
    expect(confirm).toBeDisabled();
    await userEvent.click(within(dialog).getByLabelText(/J'ai moi-même envoyé/));
    await userEvent.click(confirm);
    await waitFor(() => expect(spy.mock.calls.some((c) => (c[1] as RequestInit | undefined)?.method === "PATCH")).toBe(true));
    const patch = spy.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "PATCH")!;
    expect(String(patch[0])).toContain("applications/2");
    expect(JSON.parse((patch[1] as RequestInit).body as string)).toEqual({ status: "submitted", confirm_submission: true });
  });

  it("invite à enregistrer des offres quand la liste est vide", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json([]));
    wrap(<QueueView />);
    expect(await screen.findByText("Rien à postuler pour l'instant")).toBeInTheDocument();
  });
});
