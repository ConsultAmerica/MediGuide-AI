import { expect, test } from "@playwright/test";
import { E2E_BACKEND_URL } from "./auth-paths";

// These start signed out, unlike the rest of the suite.
test.use({ storageState: { cookies: [], origins: [] } });

test.describe("Accounts", () => {
  test("signed-out visit goes to sign in and returns to the page asked for", async ({ page }) => {
    await page.goto("/workspace/labs");
    await expect(page).toHaveURL(/\/signin\?next=%2Fworkspace%2Flabs/);
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();

    await page.getByRole("button", { name: "Try a private demo workspace" }).click();
    await expect(page).toHaveURL(/\/workspace\/labs$/);
    await expect(page.locator("aside.sidebar")).toContainText("Guest workspace");

    // Refresh keeps the session.
    await page.reload();
    await expect(page).toHaveURL(/\/workspace\/labs$/);
    await expect(page.locator("aside.sidebar")).toContainText("Guest workspace");

    await page.locator("aside.sidebar").getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/signin/);
    await page.goto("/workspace/home");
    await expect(page).toHaveURL(/\/signin\?next=/);
  });

  test("create an account, sign out, and sign back in", async ({ page }) => {
    const email = `e2e-${Date.now()}@example.com`;
    await page.goto("/signin");
    await page.getByRole("tab", { name: "Create account" }).click();
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("short");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page.locator(".signin-error")).toContainText("at least 10 characters");

    await page.getByLabel("Password").fill("a-long-enough-password");
    await page.getByRole("button", { name: "Create account" }).click();
    await expect(page).toHaveURL(/\/workspace\/home$/);
    await expect(page.locator("aside.sidebar")).toContainText(email);

    await page.locator("aside.sidebar").getByRole("button", { name: "Sign out" }).click();
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill("wrong-password-here");
    await page.getByRole("button", { name: "Sign in" }).last().click();
    await expect(page.locator(".signin-error")).toContainText("don't match");

    await page.getByLabel("Password").fill("a-long-enough-password");
    await page.getByRole("button", { name: "Sign in" }).last().click();
    await expect(page).toHaveURL(/\/workspace\/home$/);
  });

  test("a session revoked elsewhere sends the user back to sign in", async ({ page, request }) => {
    await page.goto("/signin");
    // A click before the page has hydrated does nothing; retry until it lands.
    await expect(async () => {
      if (!/\/workspace\//.test(page.url())) await page.getByRole("button", { name: "Try a private demo workspace" }).click();
      await expect(page).toHaveURL(/\/workspace\/home$/, { timeout: 3_000 });
    }).toPass({ timeout: 30_000 });

    const token = await page.evaluate(() => window.localStorage.getItem("mediguide.session"));
    await request.post(`${E2E_BACKEND_URL}/api/auth/logout`, { headers: { Authorization: `Bearer ${token}` } });

    await page.goto("/workspace/timeline");
    await expect(page).toHaveURL(/\/signin\?next=%2Fworkspace%2Ftimeline/);
  });
});
