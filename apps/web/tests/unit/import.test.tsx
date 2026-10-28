import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/toast";
import { ImportView, type ImportValues, toImportPayload } from "@/features/opportunities/import-view";
import type { ImportPreview } from "@/lib/types";

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

const preview: ImportPreview = {
  url: "https://careers.acme.example/jobs/42",
  existing_opportunity_id: null,
  fetched: true,
  method: "html",
  notes: ["Pas de données structurées : titre et description repris du contenu de la page, à relire.", "À compléter : le type."],
  draft: {
    official_url: "https://careers.acme.example/jobs/42",
    type: null,
    title: "Data Analyst – ACME",
    organization: "ACME",
    description: "Analyse de données.",
    location: null,
    countries: ["FR"],
    remote: null,
    deadline_date: "2027-03-15",
    fields: [],
    stipend: null,
  },
};

function renderView() {
  return render(<ToastProvider><ImportView /></ToastProvider>);
}

async function analyze(url = preview.url) {
  await userEvent.type(screen.getByLabelText(/Adresse de la page/), url);
  await userEvent.click(screen.getByRole("button", { name: "Analyser le lien" }));
}

describe("ajout d'une offre par lien", () => {
  it("pré-remplit le brouillon, exige le type puis envoie l'offre relue", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).includes("import/preview")
        ? json(preview)
        : json({ opportunity_id: "opp-1", created: true, application_id: "app-1", message: "Offre ajoutée au catalogue." }),
    );
    renderView();
    await analyze();
    expect(await screen.findByText("Brouillon pré-rempli : relisez chaque champ")).toBeInTheDocument();
    expect(screen.getByText("À compléter : le type.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Intitulé/)).toHaveValue("Data Analyst – ACME");
    expect(screen.getByLabelText(/^Date limite/)).toHaveValue("2027-03-15");

    await userEvent.click(screen.getByRole("button", { name: "Ajouter au catalogue" }));
    expect(await screen.findByText("Choisissez le type.")).toBeInTheDocument();
    expect(spy.mock.calls.filter((c) => String(c[0]).endsWith("opportunities/import"))).toHaveLength(0);

    await userEvent.selectOptions(screen.getByLabelText(/^Type/), "internship");
    await userEvent.click(screen.getByRole("button", { name: "Ajouter au catalogue" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/opportunities/opp-1"));
    const call = spy.mock.calls.find((c) => String(c[0]).endsWith("opportunities/import"))!;
    const body = JSON.parse((call[1] as RequestInit).body as string);
    expect(body).toMatchObject({
      type: "internship",
      title: "Data Analyst – ACME",
      countries: ["FR"],
      deadline_date: "2027-03-15",
      deadline_confirmed: false,
      follow: true,
    });
  });

  it("propose la saisie manuelle quand la page ne peut pas être lue", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json({ ...preview, fetched: false, method: "none", notes: ["Ce site n'autorise pas la lecture automatique de cette page (robots.txt)."], draft: { ...preview.draft, title: null, organization: null, description: null, countries: [], deadline_date: null } }),
    );
    renderView();
    await analyze();
    expect(await screen.findByText("Lecture automatique impossible")).toBeInTheDocument();
    expect(screen.getByText(/robots\.txt/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Lien officiel/)).toHaveValue(preview.url);
    expect(screen.getByLabelText("J'ai vérifié cette date sur la page officielle")).toBeDisabled();
  });

  it("renvoie vers l'offre existante au lieu de créer un doublon", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ ...preview, existing_opportunity_id: "opp-9" }));
    renderView();
    await analyze();
    expect(await screen.findByText("Cette offre est déjà dans le catalogue")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Voir l'offre" })).toHaveAttribute("href", "/opportunities/opp-9");
    expect(screen.queryByRole("button", { name: "Ajouter au catalogue" })).not.toBeInTheDocument();
  });

  it("affiche le refus d'un lien non public", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json({ error: { code: "invalid_link", message: "Lien refusé : cette adresse ne correspond pas à un site public." } }, 422),
    );
    renderView();
    await analyze("http://127.0.0.1/admin");
    expect(await screen.findByText(/ne correspond pas à un site public/)).toBeInTheDocument();
  });
});

describe("charge utile envoyée", () => {
  const base: ImportValues = {
    official_url: " https://x.example/o ", type: "masters_scholarship", title: " Bourse ", organization: " Univ ", location: "",
    countries: [], remote: "no", deadline_date: "", deadline_confirmed: true, duration_months: "24", funding_type: "full",
    funding_amount: "", stipend: "", study_levels: ["bachelor"], fields: [], required_documents: ["CV"],
    eligibility_criteria: "  ", description: "", follow: false,
  };

  it("convertit les champs vides en null et ne confirme jamais une date absente", () => {
    expect(toImportPayload(base)).toEqual({
      official_url: "https://x.example/o", type: "masters_scholarship", title: "Bourse", organization: "Univ", location: null,
      countries: [], remote: false, deadline_date: null, deadline_confirmed: false, duration_months: 24, funding_type: "full",
      funding_amount: null, stipend: null, study_levels: ["bachelor"], fields: [], required_documents: ["CV"],
      eligibility_criteria: null, description: null, follow: false,
    });
  });
});
