import path from "node:path";
import fs from "node:fs";
import { test, expect } from "@playwright/test";
import { confirmRemainingImagingSections, generateReportPdf, generateLabReportPdf } from "./helpers";

const FIXTURES_DIR = path.join(__dirname, ".scratch", "fixtures");

test.beforeAll(() => {
  fs.mkdirSync(FIXTURES_DIR, { recursive: true });
});

// Medication search is covered at the backend-test level
// (tests/test_search_api.py::test_search_finds_confirmed_medication) rather
// than here — seeding a confirmed MedicationRecord through the real UI
// requires the AI-dependent typed-text/upload extraction endpoint, which
// (like the rest of this E2E suite) is deliberately kept out of the
// browser-driven journey.
test.describe("Global search — Cmd/Ctrl+K", () => {
  test("search finds a lab result, opens it at the correct source page, Escape restores focus", async ({ page }) => {
    await page.goto("/workspace/documents");
    // A one-off generated reading, not data/samples/sample-lab-report.pdf —
    // that fixture is also what "Try synthetic report" loads
    // (synthetic-demo.spec.ts), and re-uploading it here would deposit a
    // second set of the same three Hemoglobin A1C dates onto the shared
    // e2e DB's trend line, breaking that spec's "exactly 3 points" check.
    const filePath = path.join(FIXTURES_DIR, "search-lab-report.pdf");
    generateLabReportPdf(filePath, { testName: "Creatinine", value: "1.1", unit: "mg/dL", referenceRange: "0.6-1.2" });
    await page.locator('input[type="file"]').first().setInputFiles(filePath);
    await expect(page.getByText(/reviewed$/)).toBeVisible({ timeout: 20_000 });
    // The upload moves to the document's own route; let that navigation land
    // (in dev it compiles on first visit) before using the review screen.
    await expect(page).toHaveURL(/\/workspace\/documents\/[0-9a-f]{32}/, { timeout: 30_000 });
    await expect(page.getByText(/reviewed$/)).toBeVisible({ timeout: 20_000 });
    // Confirm the clearly read values in one step (behind a dialog), then
    // decide anything left individually: every value needs a decision.
    await page.getByRole("button", { name: /Confirm clearly read values/ }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: /^Confirm \d+ values?$/ }).click();
    const remaining = page.locator(".field-review-actions").getByRole("button", { name: "Confirm", exact: true });
    for (let guard = 0; guard < 50 && (await remaining.count()) > 0; guard += 1) await remaining.first().click();
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "Confirm reviewed items" }).click();
    await expect(page.locator(".eyebrow", { hasText: "CONFIRMED" })).toBeVisible({ timeout: 15_000 });

    // Focus a known element first so we can prove Escape restores it.
    const documentsNav = page.locator("aside").getByRole("button", { name: "Documents", exact: true });
    await documentsNav.focus();

    await page.keyboard.press("Control+k");
    const input = page.getByRole("combobox", { name: "Search your health information" });
    await expect(input).toBeFocused();

    await input.fill("creatinine");
    await expect(page.getByText("LAB RESULTS")).toBeVisible({ timeout: 10_000 });
    const result = page.getByRole("option").filter({ hasText: "Lab Report" });
    await expect(result).toBeVisible();
    await result.click();

    // Lands on the document at the correct source page — a real URL, not
    // just in-memory state. Selecting a result closes the palette the same
    // way Escape does, so this also proves focus returns to whatever was
    // focused before Cmd/Ctrl+K (checked here, before the reload below,
    // since a hard reload legitimately wipes any prior focus state).
    await expect(page).toHaveURL(/\/workspace\/documents\/[a-f0-9-]+\?page=\d+/);
    await expect(documentsNav).toBeFocused();

    // The URL — not just in-memory state — is what makes the page/field
    // survive a refresh.
    const detailUrl = page.url();
    await page.reload();
    await expect(page).toHaveURL(detailUrl);
    await expect(page.getByText("Creatinine", { exact: false }).first()).toBeVisible();

    // Escape also restores focus, independent of the reload above.
    const documentsNavAfterReload = page.locator("aside").getByRole("button", { name: "Documents", exact: true });
    await documentsNavAfterReload.focus();
    await page.keyboard.press("Control+k");
    const input2 = page.getByRole("combobox", { name: "Search your health information" });
    await expect(input2).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(input2).not.toBeVisible();
    await expect(documentsNavAfterReload).toBeFocused();
  });

  test("search finds an imaging study and opens the real Imaging Detail view", async ({ page }) => {
    // Navigate straight to /workspace/imaging rather than /workspace itself
    // — the bare /workspace route does a client-side redirect to
    // /workspace/home on mount, and racing that against an immediate
    // sidebar click becomes flaky once the shared e2e DB (see the file
    // comment on timeline-pagination.spec.ts) is carrying enough records to
    // slow the redirect's own data fetch.
    await page.goto("/workspace/imaging");
    await expect(page.getByRole("button", { name: "Add imaging study" })).toBeEnabled();
    await page.getByRole("button", { name: "Add imaging study" }).click();
    await page.locator(".imaging-add-form select").selectOption("mri");
    await page.getByPlaceholder("e.g. Right knee").fill("Right Knee");
    await page.getByRole("button", { name: "Create study" }).click();

    const reportPath = path.join(FIXTURES_DIR, "search-imaging-report.pdf");
    generateReportPdf(reportPath, {
      exam: "MRI Right Knee",
      findings: "Small joint effusion.",
      impression: "Small joint effusion.",
    });
    await page.locator(".imaging-upload-label input[type=file]").setInputFiles(reportPath);
    await expect(page.getByText(/sections reviewed/)).toBeVisible({ timeout: 20_000 });
    await confirmRemainingImagingSections(page);
    await expect(page.locator(".lab-verified")).toContainText("Verified");

    await page.keyboard.press("Control+k");
    const input = page.getByRole("combobox", { name: "Search your health information" });
    await input.fill("mri");
    await expect(page.locator(".command-palette-group-label", { hasText: "IMAGING" }).first()).toBeVisible({ timeout: 10_000 });
    await page.getByRole("option").filter({ hasText: "MRI — Right Knee" }).first().click();

    await expect(page).toHaveURL(/\/workspace\/imaging\/[a-f0-9-]+$/);
    await expect(page.locator(".imaging-study-meta")).toContainText("MRI");
  });

  test.describe("mobile", () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test("search opens as a full-screen sheet with a visible trigger", async ({ page }) => {
      await page.goto("/workspace/home");
      // The shell (and its Ctrl+K listener) mounts once the session check resolves.
      await expect(page.locator(".app-header")).toBeVisible();
      await page.keyboard.press("Control+k");
      const input = page.getByRole("combobox", { name: "Search your health information" });
      await expect(input).toBeFocused();
      const box = await input.boundingBox();
      expect(box?.width).toBeGreaterThan(300); // near-full 390px viewport width, not a small centered dialog
      await page.keyboard.press("Escape");
      await expect(input).not.toBeVisible();
    });
  });
});
