import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { SWRConfig } from "swr";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "@/features/auth/login-form";
import { RegisterForm, VerifyEmailForm } from "@/features/auth/register-form";

let search = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => search,
  usePathname: () => "/",
}));

afterEach(() => {
  vi.restoreAllMocks();
  search = new URLSearchParams();
});

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

/** Cache SWR isolé par test (la configuration publique change d'un test à l'autre). */
const wrap = (ui: ReactNode) => render(<SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>{ui}</SWRConfig>);

function mockApi(open: boolean, handler: (url: string, init?: RequestInit) => Response = () => json({})) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("auth/config")) return json({ registration_open: open });
    return handler(url, init);
  });
}

const calls = (spy: ReturnType<typeof mockApi>, fragment: string) => spy.mock.calls.filter((c) => String(c[0]).includes(fragment));

describe("inscription", () => {
  it("indique que les inscriptions sont fermées", async () => {
    mockApi(false);
    wrap(<RegisterForm />);
    expect(await screen.findByText("Inscriptions fermées")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Créer mon compte" })).not.toBeInTheDocument();
  });

  it("valide le formulaire puis envoie uniquement les champs utiles", async () => {
    const spy = mockApi(true, () => json({ message: "Un e-mail de confirmation vient d'être envoyé." }, 202));
    wrap(<RegisterForm />);
    const submit = await screen.findByRole("button", { name: "Créer mon compte" });
    await userEvent.type(screen.getByLabelText(/Adresse e-mail/), "awa@example.com");
    await userEvent.type(screen.getByLabelText(/^Mot de passe/), "Mot-de-passe-solide-2026");
    await userEvent.type(screen.getByLabelText(/^Confirmation/), "Autre-mot-de-passe-2026");
    await userEvent.click(submit);
    expect(await screen.findByText("Les mots de passe ne correspondent pas.")).toBeInTheDocument();
    expect(screen.getByText("Acceptation requise pour créer un compte.")).toBeInTheDocument();
    expect(calls(spy, "auth/register")).toHaveLength(0);

    await userEvent.clear(screen.getByLabelText(/^Confirmation/));
    await userEvent.type(screen.getByLabelText(/^Confirmation/), "Mot-de-passe-solide-2026");
    await userEvent.click(screen.getByLabelText(/J'accepte/));
    await userEvent.click(submit);
    expect(await screen.findByText("Vérifiez votre boîte e-mail")).toBeInTheDocument();
    const body = JSON.parse((calls(spy, "auth/register")[0]![1] as RequestInit).body as string);
    expect(body).toEqual({ email: "awa@example.com", password: "Mot-de-passe-solide-2026", display_name: null });
  });
});

describe("connexion et confirmation d'adresse", () => {
  it("propose l'inscription seulement si elle est ouverte", async () => {
    mockApi(true);
    wrap(<LoginForm />);
    expect(await screen.findByRole("link", { name: "Créer un compte" })).toHaveAttribute("href", "/register");
  });

  it("propose un nouvel envoi du lien si l'adresse n'est pas confirmée", async () => {
    mockApi(false, (url) =>
      url === "/api/auth/login"
        ? json({ error: { code: "email_not_verified", message: "Adresse e-mail non confirmée." } }, 403)
        : json({ message: "Nouvel e-mail envoyé." }, 202),
    );
    wrap(<LoginForm />);
    await userEvent.type(screen.getByLabelText(/Adresse e-mail/), "awa@example.com");
    await userEvent.type(screen.getByLabelText(/Mot de passe/), "Mot-de-passe-solide-2026");
    await userEvent.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByText("Adresse e-mail non confirmée.")).toBeInTheDocument();
    expect(screen.getByLabelText("Recevoir un nouveau lien de confirmation")).toHaveValue("awa@example.com");
    await userEvent.click(screen.getByRole("button", { name: "Renvoyer le lien" }));
    expect(await screen.findByText("Nouvel e-mail envoyé.")).toBeInTheDocument();
  });

  it("confirme l'adresse uniquement après un clic", async () => {
    search = new URLSearchParams({ token: "jeton-de-confirmation-0123456789" });
    const spy = mockApi(false, () => json({ message: "Adresse confirmée. Vous pouvez vous connecter." }));
    wrap(<VerifyEmailForm />);
    expect(calls(spy, "auth/verify-email")).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Confirmer mon adresse" }));
    await waitFor(() => expect(calls(spy, "auth/verify-email")).toHaveLength(1));
    expect(JSON.parse((calls(spy, "auth/verify-email")[0]![1] as RequestInit).body as string)).toEqual({ token: "jeton-de-confirmation-0123456789" });
    expect(await screen.findByText("Adresse confirmée")).toBeInTheDocument();
  });
});
