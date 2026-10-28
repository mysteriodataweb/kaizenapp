import { defineConfig, devices } from "@playwright/test";

/**
 * Parcours critiques de bout en bout. Les serveurs (API + Next.js) et la base e2e locale
 * sont préparés par scripts/e2e.sh ; ce fichier ne démarre rien lui-même.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3001",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] }, testIgnore: /(responsive|import)\.spec\.ts/ },
    // Ajoute des offres au catalogue partagé : exécuté après les parcours qui vérifient les volumes de la base e2e.
    { name: "desktop-catalogue-writes", use: { ...devices["Desktop Chrome"] }, testMatch: /import\.spec\.ts/, dependencies: ["desktop"] },
    { name: "mobile", use: { ...devices["Pixel 7"] }, testMatch: /responsive\.spec\.ts/ },
  ],
});
