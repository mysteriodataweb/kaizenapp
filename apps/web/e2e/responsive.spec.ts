import { expect, test } from "@playwright/test";

import { login } from "./helpers";

const PAGES = ["/dashboard", "/opportunities", "/matches", "/applications", "/calendar", "/documents", "/profile", "/notifications", "/settings", "/admin/users", "/opportunities/new", "/queue"];

test("mobile : menu compact et aucune page ne déborde horizontalement", async ({ page }) => {
  await login(page);
  await page.getByRole("button", { name: "Menu" }).click();
  await page.getByRole("dialog", { name: "Menu" }).getByRole("link", { name: "Opportunités" }).click();
  await expect(page).toHaveURL(/\/opportunities/);
  await expect(page.getByRole("dialog", { name: "Menu" })).toBeHidden();
  for (const path of PAGES) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(overflow, `débordement sur ${path}`).toBeLessThanOrEqual(1);
  }
});
