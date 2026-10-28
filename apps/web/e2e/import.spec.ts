import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test("liens LinkedIn enregistrés d'un coup puis traités un par un dans « À postuler »", async ({ page }) => {
  const stamp = Date.now().toString().slice(-6);
  const first = `https://www.linkedin.com/jobs/view/stage-marketing-at-acme-40${stamp}01`;
  const second = `https://www.linkedin.com/jobs/view/40${stamp}02/?trackingId=abc`;

  await login(page);
  await page.goto("/opportunities");
  await page.getByRole("link", { name: "Enregistrer des offres" }).click();
  await expect(page).toHaveURL(/\/opportunities\/new$/);
  await page.getByLabel(/Liens des offres/).fill(`${first}\n${second}`);
  await page.getByRole("button", { name: "Enregistrer 2 liens" }).click();
  await expect(page.getByText(/2 enregistrée\(s\) · 0 déjà présente\(s\) · 0 erreur\(s\)/)).toBeVisible();

  await page.getByRole("link", { name: "Commencer à postuler" }).click();
  await expect(page).toHaveURL(/\/queue$/);
  await expect(page.getByRole("heading", { name: "Stage marketing" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Ouvrir l'offre/ })).toHaveAttribute("href", `https://www.linkedin.com/jobs/view/40${stamp}01`);

  await page.getByRole("button", { name: "Plus tard" }).click();
  await expect(page.getByRole("heading", { name: `Offre LinkedIn n° 40${stamp}02` })).toBeVisible();
  await page.getByRole("button", { name: "J'ai postulé" }).click();
  const dialog = page.getByRole("dialog", { name: "Candidature envoyée ?" });
  await dialog.getByLabel(/J'ai moi-même envoyé/).check();
  await dialog.getByRole("button", { name: "Confirmer" }).click();
  await expect(page.getByText("Candidature marquée comme envoyée.")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Stage marketing" })).toBeVisible();
});

test("offre détaillée à partir du texte collé, puis modification et suppression", async ({ page }) => {
  // Domaine réservé (.invalid) : jamais résolu, aucun site externe contacté ; e2e sans IA (règles simples).
  const url = `https://offres.example.invalid/stage-${Date.now()}`;
  page.on("dialog", (d) => void d.accept());

  await login(page);
  await page.goto("/opportunities/new");
  await page.getByRole("radio", { name: "Une offre détaillée" }).click();
  await page.getByLabel(/Adresse de la page/).fill(url);
  await page.getByLabel(/Texte de l'offre/).fill("Stage analyste\nMissions : données.\nDate limite : 20 mai 2031");
  await page.getByRole("button", { name: "Analyser" }).click();
  await expect(page.getByText(/Nom de domaine introuvable/)).toBeVisible();
  await expect(page.getByLabel(/^Date limite/)).toHaveValue("2031-05-20");

  await page.getByLabel(/^Type/).selectOption("internship");
  await page.getByLabel(/^Organisme/).fill("Organisme e2e");
  await page.getByLabel(/^Intitulé/).fill("Stage e2e par texte collé");
  await page.getByRole("button", { name: "Enregistrer l'offre" }).click();

  await expect(page).toHaveURL(/\/opportunities\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("heading", { name: "Stage e2e par texte collé" })).toBeVisible();
  await expect(page.getByText("Offre personnelle")).toBeVisible();

  await page.getByRole("link", { name: "Modifier" }).click();
  await page.getByLabel(/^Intitulé/).fill("Stage e2e modifié");
  await page.getByRole("button", { name: "Enregistrer les modifications" }).click();
  await expect(page.getByRole("heading", { name: "Stage e2e modifié" })).toBeVisible();

  await page.getByRole("button", { name: "Supprimer" }).click();
  await expect(page).toHaveURL(/\/queue$/);
  await expect(page.getByText("Stage e2e modifié")).toHaveCount(0);
});
