import path from "node:path";
import { test, expect } from "@playwright/test";

const REPO_ROOT = path.resolve(__dirname, "..", "..");

/** Regression coverage for the production bug where "Try synthetic data"
 * failed with "Document upload failed / Sample lab report is unavailable."
 * Root cause: .dockerignore excluded data/samples from the Docker build
 * context, so the shipped fixture was silently absent in the deployed
 * container despite being committed to git and present locally. This test
 * exercises the real, full canonical journey end to end — synthetic PDF
 * through the same upload/extraction/verification/timeline pipeline as any
 * other document — not a mocked shortcut. */

test.describe("Synthetic demo — canonical journey", () => {
  test("Try synthetic data through Documents, review, confirm, and reach Lab Timeline with source provenance", async ({ page }) => {
    await page.goto("/workspace");
    // Next 16's streaming hydration can paint the sidebar before its click
    // handlers are attached (see imaging-happy-path.spec.ts for the same
    // issue) — wait for it to be interactive first.
    const documentsNav = page.locator("aside").getByRole("button", { name: "Documents", exact: true });
    await expect(documentsNav).toBeEnabled();
    await documentsNav.click();

    await page.getByRole("button", { name: "Try synthetic report" }).first().click();

    // The actual bug surfaced here: this used to show
    // "Document upload failed" / "Sample lab report is unavailable."
    await expect(page.getByText("Document upload failed")).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByText("We couldn't prepare the synthetic reports")).toHaveCount(0);

    // Extraction runs (native-text PDF, no Ollama dependency) then lands on
    // the verification view with real extracted fields.
    await expect(page.getByText(/reviewed$/)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Hemoglobin A1C", { exact: false }).first()).toBeVisible();

    // Review every field, then confirm.
    const reviewButtons = page.locator(".field-review-actions").getByRole("button", { name: "Confirm" });
    const fieldCount = await reviewButtons.count();
    for (let i = 0; i < fieldCount; i += 1) {
      await reviewButtons.nth(i).click();
    }
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "Confirm reviewed items" }).click();
    await expect(page.locator(".eyebrow", { hasText: "CONFIRMED" })).toBeVisible({ timeout: 15_000 });

    // Labs: three synthetic dates, selectable, with source drill-down.
    await page.locator("aside").getByRole("button", { name: "Labs", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Labs" })).toBeVisible();
    // Chart points are buttons named "<value> <unit>, <date>. Open provenance".
    const points = page.locator(".lab-trend-chart").getByRole("button", { name: /Open provenance/ });
    await expect(points).toHaveCount(3, { timeout: 15_000 });

    // Aug 12 is the latest/rightmost synthetic point — select it directly.
    await points.filter({ hasText: "6.7" }).click();
    await expect(page.getByText("6.7", { exact: false }).first()).toBeVisible();

    await page.getByRole("button", { name: "View source page" }).click();
    // Landing on the source document view proves the synthetic report is a
    // real, stored Document — not a fabricated frontend-only result.
    await expect(page.getByText(/PAGE \d/).first()).toBeVisible({ timeout: 10_000 });
  });

  // Demo success uses a fetch-then-upload path; a normal "Choose file"
  // upload is a genuinely different code path (real <input type=file>,
  // no /sample/lab-report round trip first) and must be verified
  // independently rather than assumed from the demo passing.
  test("a normal file upload (not the synthetic demo) also completes extraction", async ({ page }) => {
    await page.goto("/workspace");
    const documentsNav = page.locator("aside").getByRole("button", { name: "Documents", exact: true });
    await expect(documentsNav).toBeEnabled();
    await documentsNav.click();

    const filePath = path.join(REPO_ROOT, "data", "samples", "sample-lab-report.pdf");
    await page.locator('input[type="file"]').first().setInputFiles(filePath);

    await expect(page.getByText("Document upload failed")).toHaveCount(0, { timeout: 15_000 });
    await expect(page.getByText(/reviewed$/)).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Hemoglobin A1C", { exact: false }).first()).toBeVisible();
  });
});
