import { expect, type Page } from "@playwright/test";

export const E2E_EMAIL = "e2e@example.com";
export const E2E_PASSWORD = "E2e-Mot-de-passe-2026";

export async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Adresse e-mail").fill(E2E_EMAIL);
  await page.getByLabel("Mot de passe").fill(E2E_PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}
