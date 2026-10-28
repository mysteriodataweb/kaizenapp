import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("ajout d'une offre par lien : saisie manuelle si la page est illisible, provenance, doublon détecté", async ({ page }) => {
  // Domaine réservé (.invalid) : jamais résolu, aucun site externe contacté.
  const url = `https://offres.example.invalid/stage-${Date.now()}`;
  const title = "Stage e2e ajouté par lien";

  await login(page);
  await page.goto("/opportunities");
  await page.getByRole("link", { name: "Ajouter une offre" }).click();
  await expect(page).toHaveURL(/\/opportunities\/new$/);
  await page.getByLabel(/Adresse de la page/).fill(url);
  await page.getByRole("button", { name: "Analyser le lien" }).click();
  await expect(page.getByText("Lecture automatique impossible")).toBeVisible();
  await expect(page.getByText(/Nom de domaine introuvable/)).toBeVisible();

  await page.getByLabel(/^Type/).selectOption("internship");
  await page.getByLabel(/^Organisme/).fill("Organisme e2e");
  await page.getByLabel(/^Intitulé/).fill(title);
  await page.getByLabel(/^Date limite/).fill("2031-05-20");
  await page.getByRole("button", { name: "Ajouter au catalogue" }).click();

  await expect(page).toHaveURL(/\/opportunities\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  await expect(page.getByText(/Ajouts manuels/).first()).toBeVisible();

  await page.goto("/opportunities/new");
  await page.getByLabel(/Adresse de la page/).fill(url);
  await page.getByRole("button", { name: "Analyser le lien" }).click();
  await expect(page.getByText("Cette offre est déjà dans le catalogue")).toBeVisible();
});
