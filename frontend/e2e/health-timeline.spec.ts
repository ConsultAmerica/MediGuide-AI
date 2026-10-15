import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import { confirmRemainingImagingSections, generateReportPdf } from "./helpers";

const FIXTURES_DIR = path.join(__dirname, ".scratch", "fixtures");

test.beforeAll(() => {
  fs.mkdirSync(FIXTURES_DIR, { recursive: true });
});

test.describe("Health Timeline", () => {
  test("shows confirmed items and cross-links into their real detail views", async ({ page }) => {
    // Seed one confirmed, verified imaging study through the real Imaging flow.
    // Navigating straight to /workspace/imaging (rather than /workspace,
    // which client-redirects to /workspace/home on mount) avoids a race
    // between that redirect and an immediate sidebar click — one that gets
    // more likely to lose the race as the shared e2e DB accumulates more
    // records from other spec files and API responses slow down.
    await page.goto("/workspace/imaging");
    await expect(page.getByRole("button", { name: "Add imaging study" })).toBeEnabled();
    await page.getByRole("button", { name: "Add imaging study" }).click();
    await page.locator(".imaging-add-form select").selectOption("ultrasound");
    await page.getByPlaceholder("e.g. Right knee").fill("Abdomen");
    await page.getByRole("button", { name: "Create study" }).click();

    const reportPath = path.join(FIXTURES_DIR, "timeline-imaging-report.pdf");
    generateReportPdf(reportPath, {
      exam: "Ultrasound Abdomen",
      findings: "No acute abnormality.",
      impression: "No acute abnormality.",
    });
    await page.locator(".imaging-upload-label input[type=file]").setInputFiles(reportPath);
    await expect(page.getByText(/sections reviewed/)).toBeVisible({ timeout: 20_000 });

    await confirmRemainingImagingSections(page);
    await expect(page.locator(".lab-verified")).toContainText("Verified");

    // Open the Health Timeline and confirm the study appears.
    await page.locator("aside").getByRole("button", { name: "Health Timeline", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Health Timeline" })).toBeVisible();
    const imagingRow = page.locator(".timeline-entry").filter({ hasText: "Ultrasound" });
    await expect(imagingRow).toBeVisible();
    await expect(imagingRow).toContainText("Verified report");

    // "View study" cross-links into the real Imaging Detail view.
    await imagingRow.getByRole("button", { name: "View study" }).click();
    await expect(page.locator(".imaging-study-meta")).toContainText("Ultrasound");

    // Back to the Timeline for the empty/no-entries copy check on a fresh
    // reload isn't meaningful here (data now exists), so instead verify the
    // dismissible error banner never appears when the API is healthy.
    await page.locator("aside").getByRole("button", { name: "Health Timeline", exact: true }).click();
    await expect(page.getByText("Something needs attention")).toHaveCount(0);

    // Filter bar: switching to "Labs" hides the imaging entry; "All" (via
    // Clear filters) brings it back.
    await expect(page.locator(".timeline-entry").filter({ hasText: "Ultrasound" })).toBeVisible();
    await page.getByRole("tab", { name: "Labs" }).click();
    await expect(page).toHaveURL(/type=laboratory/);
    await expect(page.locator(".timeline-entry").filter({ hasText: "Ultrasound" })).toHaveCount(0);
    // Filtering to a type with no matches also triggers the empty state's
    // own "Clear filters" button, so scope to the persistent filter bar's.
    await page.locator(".timeline-filter-fields").getByRole("button", { name: "Clear filters" }).click();
    await expect(page).not.toHaveURL(/type=laboratory/);
    await expect(page.locator(".timeline-entry").filter({ hasText: "Ultrasound" })).toBeVisible();
  });
});
