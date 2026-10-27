import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("inscription : compte créé en attente de confirmation, connexion refusée, visible par l'administrateur", async ({ page }) => {
  const email = `inscrit-${Date.now()}@example.com`;
  const password = "Inscription-solide-2026";

  await page.goto("/login");
  await page.getByRole("link", { name: "Créer un compte" }).click();
  await expect(page).toHaveURL(/\/register$/);
  await page.getByLabel("Nom affiché").fill("Nouvelle personne");
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel(/^Mot de passe/).fill(password);
  await page.getByLabel(/^Confirmation/).fill(password);
  await page.getByLabel(/J'accepte/).check();
  await page.getByRole("button", { name: "Créer mon compte" }).click();
  await expect(page.getByText("Vérifiez votre boîte e-mail")).toBeVisible();

  // Adresse non confirmée : la connexion est refusée et un nouvel envoi est proposé.
  await page.goto("/login");
  await page.getByLabel("Adresse e-mail").fill(email);
  await page.getByLabel("Mot de passe").fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByText(/Adresse e-mail non confirmée/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Renvoyer le lien" })).toBeVisible();

  await login(page);
  await page.goto("/admin/users");
  const row = page.getByRole("row").filter({ hasText: email });
  await expect(row).toContainText("En attente de confirmation");
  await expect(row.getByRole("button", { name: "Désactiver" })).toBeVisible();
});

test("lien de confirmation invalide : message clair et nouvel envoi possible", async ({ page }) => {
  await page.goto("/verify-email?token=jeton-invalide-0123456789abcdef");
  await page.getByRole("button", { name: "Confirmer mon adresse" }).click();
  await expect(page.getByText("Lien de confirmation invalide ou expiré.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Renvoyer le lien" })).toBeVisible();
});
