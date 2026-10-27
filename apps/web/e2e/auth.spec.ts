import { expect, test } from "@playwright/test";

import { E2E_EMAIL, login } from "./helpers";

test("les pages privées redirigent vers la connexion", async ({ page }) => {
  await page.goto("/applications");
  await expect(page).toHaveURL(/\/login\?next=%2Fapplications/);
  await expect(page.getByRole("heading", { name: "Connexion" })).toBeVisible();
});

test("un mauvais mot de passe est refusé sans divulguer d'information", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Adresse e-mail").fill(E2E_EMAIL);
  await page.getByLabel("Mot de passe").fill("mauvais-mot-de-passe");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByText("Identifiants invalides.")).toBeVisible();
});

test("le jeton de session n'est jamais lisible par le JavaScript", async ({ page, context }) => {
  await login(page);
  const cookie = (await context.cookies()).find((c) => c.name === "oi_session");
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Lax");
  expect(await page.evaluate(() => document.cookie)).not.toContain("oi_session");
});

test("la passerelle refuse les requêtes d'une autre origine (CSRF)", async ({ page, request }) => {
  await login(page);
  const cookies = await page.context().cookies();
  const session = cookies.find((c) => c.name === "oi_session")!;
  const res = await request.patch("/api/backend/profile", {
    headers: { Origin: "https://attaquant.example", Cookie: `oi_session=${session.value}` },
    data: { full_name: "Pirate" },
  });
  expect(res.status()).toBe(403);
});

test("déconnexion", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Se déconnecter" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login/);
});
