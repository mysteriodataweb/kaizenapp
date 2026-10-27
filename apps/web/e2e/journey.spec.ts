import { expect, test } from "@playwright/test";

import { login } from "./helpers";

test.describe.configure({ mode: "serial" });

test("collecte -> matching -> catalogue -> suivi -> statut -> tâche -> alertes", async ({ page }) => {
  await login(page);

  // Tableau de bord alimenté par la collecte (pipeline réel sur jeux de test)
  await expect(page.getByText("Opportunités ouvertes")).toBeVisible();

  // Catalogue : filtre par type, côté serveur
  await page.goto("/opportunities");
  await expect(page.getByText(/5 résultats/)).toBeVisible();
  await page.getByRole("button", { name: /Filtres/ }).click();
  await page.getByLabel("Type").selectOption("internship");
  await expect(page).toHaveURL(/type=internship/);
  await expect(page.getByText(/2 résultats/)).toBeVisible();

  // Recherche plein texte
  await page.getByLabel("Rechercher").fill("Data Science");
  await expect(page.getByRole("heading", { name: "Data Science Internship" })).toBeVisible();

  // Détail : provenance + explication du score
  await page.getByRole("link", { name: "Data Science Internship" }).click();
  await expect(page.getByRole("heading", { name: "Analyse de compatibilité" })).toBeVisible();
  await expect(page.getByText("A. Éligibilité")).toBeVisible();
  await expect(page.getByText(/pas une probabilité d'acceptation/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Provenance" })).toBeVisible();

  // Ajout au suivi
  await page.getByRole("button", { name: "Ajouter au suivi" }).click();
  await page.getByRole("link", { name: "Voir ma candidature" }).click();
  await expect(page).toHaveURL(/\/applications\//);

  // Changement de statut avec validation humaine
  await page.getByLabel("Statut", { exact: true }).selectOption("submitted");
  const dialog = page.getByRole("dialog", { name: "Confirmer l'envoi" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Confirmer" })).toBeDisabled();
  await dialog.getByLabel(/J'ai moi-même envoyé/).check();
  await dialog.getByRole("button", { name: "Confirmer" }).click();
  await expect(page.getByText("Statut : Envoyée")).toBeVisible();

  // Tâche
  await page.getByLabel("Nouvelle tâche").fill("Relancer le recruteur");
  await page.getByRole("button", { name: "Ajouter" }).click();
  await expect(page.getByText("Relancer le recruteur", { exact: true })).toBeVisible();
  await expect(page.getByText("Tâche créée")).toBeVisible();

  // Pipeline : vue tableau et kanban
  await page.goto("/applications");
  await expect(page.getByRole("heading", { name: /Envoyée/ })).toBeVisible();
  await page.getByRole("radio", { name: "Tableau" }).click();
  await expect(page.getByRole("table")).toBeVisible();

  // Préférences d'alertes + aperçu sans envoi
  await page.goto("/notifications");
  await expect(page.getByText("Mode simulation : les e-mails réels ne sont pas actifs")).toBeVisible();
  await page.getByLabel("Score minimal").fill("40");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("Modifications enregistrées.")).toBeVisible();
  await page.getByRole("button", { name: "Aperçu du récapitulatif" }).click();
  await expect(page.frameLocator("iframe[title=\"Aperçu de l'e-mail\"]").getByText("Opportunity Intelligence")).toBeVisible();
});

test("profil : modification, validation et recalcul", async ({ page }) => {
  await login(page);
  await page.goto("/profile");
  await page.getByLabel("Établissement").fill("Université Cheikh Anta Diop");
  await page.getByLabel("Durée de stage min. (mois)").fill("6");
  await page.getByLabel("Durée max. (mois)").fill("3");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText("La durée maximale doit être supérieure à la minimale.")).toBeVisible();
  await page.getByLabel("Durée max. (mois)").fill("6");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/Profil enregistré/)).toBeVisible();
});

test("calendrier, documents, administration", async ({ page }) => {
  await login(page);
  await page.goto("/calendar");
  await expect(page.getByRole("heading", { name: "Calendrier" })).toBeVisible();
  await page.goto("/documents");
  await page.getByRole("button", { name: "Téléverser" }).first().click();
  const dialog = page.getByRole("dialog", { name: "Téléverser un document" });
  await dialog.getByLabel("Fichier").setInputFiles({ name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("Lettre de motivation (brouillon)") });
  await dialog.getByLabel("Type").selectOption("cover_letter");
  await dialog.getByRole("button", { name: "Téléverser" }).click();
  await expect(page.getByText("Document ajouté.")).toBeVisible();
  await page.goto("/admin/sources");
  await expect(page.getByRole("heading", { name: "Sources de veille" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Erasmus Mundus — catalogue officiel (EACEA)" })).toBeVisible();
});
