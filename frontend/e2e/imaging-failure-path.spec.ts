import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import { generateReportPdf, sidebarImagingNav } from "./helpers";

const FIXTURES_DIR = path.join(__dirname, ".scratch", "fixtures");

test.beforeAll(() => {
  fs.mkdirSync(FIXTURES_DIR, { recursive: true });
});

async function openImagingAndCreateStudy(page: import("@playwright/test").Page, modality = "mri") {
  await page.goto("/workspace");
  // Wait for hydration to finish before the first interaction — Next 16's
  // streaming hydration can paint the sidebar before its click handlers are
  // attached (see imaging-happy-path.spec.ts).
  await expect(sidebarImagingNav(page)).toBeEnabled();
  await sidebarImagingNav(page).click();
  await page.getByRole("button", { name: "Add imaging study" }).click();
  await page.locator(".imaging-add-form select").selectOption(modality);
  await page.getByPlaceholder("e.g. Right knee").fill("Right knee");
  await page.getByRole("button", { name: "Create study" }).click();
  await expect(page.locator(".imaging-study-meta")).toBeVisible();
}

test.describe("Imaging — failure paths", () => {
  test("unsupported .dcm upload shows a friendly notice, never the raw error code", async ({ page }) => {
    await openImagingAndCreateStudy(page);
    const dcmPath = path.join(FIXTURES_DIR, "scan.dcm");
    fs.writeFileSync(dcmPath, Buffer.from("not-really-dicom"));

    await page.locator(".imaging-upload-label input[type=file]").setInputFiles(dcmPath);

    await expect(page.locator(".empty-state-panel strong", { hasText: "DICOM viewing isn't available yet" })).toBeVisible();
    await expect(page.getByText("DICOM_NOT_YET_SUPPORTED")).toHaveCount(0);
    // This is a styled <label> wrapping a hidden file input, not a <button>
    // role, since it must itself be a native file-picker trigger.
    await expect(page.getByText("Upload imaging report instead")).toBeVisible();
  });

  test("malformed PDF fails safely with a retry affordance, original attempt preserved", async ({ page }) => {
    await openImagingAndCreateStudy(page);
    const badPdfPath = path.join(FIXTURES_DIR, "malformed.pdf");
    generateReportPdf(badPdfPath, { invalid: true });

    await page.locator(".imaging-upload-label input[type=file]").setInputFiles(badPdfPath);

    await expect(page.getByText("We couldn’t finish reading this imaging report.")).toBeVisible({
      timeout: 20_000,
    });
    await expect(page.getByText("Your original report is still available.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Retry processing" })).toBeVisible();
  });

  // "No recognized headers → empty result, never a guess" is deterministically
  // covered at the unit level (tests/test_imaging_sections.py::
  // test_unknown_headers_return_empty_rather_than_guessing). It is not
  // re-tested here at the E2E layer: native text with no recognized headers
  // falls through to the vision-OCR fallback (a real, intentional behavior —
  // the extractor gets a second attempt via the vision model before giving
  // up), which depends on a live Ollama instance and would make this
  // specific E2E scenario's outcome depend on whether Ollama is installed
  // and what the vision model returns for deliberately unstructured text —
  // non-deterministic in a way the unit test correctly avoids.

  test("a report with only some known sections shows only those, never a fabricated one", async ({ page }) => {
    await openImagingAndCreateStudy(page);
    const partialPath = path.join(FIXTURES_DIR, "partial-sections.pdf");
    generateReportPdf(partialPath, { exam: "MRI Right Knee", findings: "No acute fracture." });

    await page.locator(".imaging-upload-label input[type=file]").setInputFiles(partialPath);
    await expect(page.getByText(/sections reviewed/)).toBeVisible({ timeout: 20_000 });

    await expect(page.getByLabel("Exam")).toBeVisible();
    await expect(page.getByLabel("Findings")).toBeVisible();
    await expect(page.getByLabel("Impression")).toHaveCount(0);
    await expect(page.getByLabel("Technique")).toHaveCount(0);
  });

  test("missing source page preview shows the honest fallback, never a fake highlight", async ({ page }) => {
    await openImagingAndCreateStudy(page);
    const reportPath = path.join(FIXTURES_DIR, "for-missing-preview.pdf");
    generateReportPdf(reportPath, { exam: "MRI Right Knee", findings: "No acute fracture." });
    // The page preview can't be served (e.g. its file was cleared).
    await page.route("**/report/pages/*/preview", (route) => route.fulfill({ status: 404, body: "" }));
    await page.locator(".imaging-upload-label input[type=file]").setInputFiles(reportPath);
    await expect(page.getByText(/sections reviewed/)).toBeVisible({ timeout: 20_000 });

    // Page navigation stops at the report's last page (this fixture has one).
    await expect(page.getByRole("button", { name: "Next page" }).first()).toBeDisabled();
    // Selecting a section must not draw an outline over a page that isn't shown.
    await page.locator(".imaging-section-title").first().click();
    // The image load fails and the viewer swaps in the honest fallback —
    // never a broken-image icon, never a fabricated highlight.
    const viewer = page.locator(".imaging-viewer").first();
    await expect(viewer.getByText("No preview is available for this page.")).toBeVisible({
      timeout: 10_000,
    });
    await expect(viewer.locator("img")).toHaveCount(0);
    await expect(viewer.locator(".imaging-source-region")).toHaveCount(0);
  });

  test("comparing an unconfirmed report is rejected with a clear message", async ({ page }) => {
    // Uses PET/CT specifically (not MRI): the happy-path spec seeds and
    // confirms MRI studies against this same shared backend/database, so a
    // modality no other spec touches is the only reliable way to assert
    // "zero verified studies of this modality" without cross-file pollution.
    await openImagingAndCreateStudy(page, "pet_ct");
    const reportPath = path.join(FIXTURES_DIR, "unverified-for-compare.pdf");
    generateReportPdf(reportPath, { exam: "PET/CT Whole Body", findings: "No acute abnormality.", impression: "No acute abnormality." });
    await page.locator(".imaging-upload-label input[type=file]").setInputFiles(reportPath);
    await expect(page.getByText(/sections reviewed/)).toBeVisible({ timeout: 20_000 });
    // Deliberately do NOT confirm — go straight to History.

    await page.getByRole("button", { name: "View history" }).click();
    // An unverified study never gets a "Compare with another study" action.
    // Scoped to this specific study's row, not the whole History page —
    // other (MRI) studies confirmed by other tests sharing this same
    // backend/database legitimately do have the action on their own rows.
    const petCtRow = page.locator(".imaging-history-row").filter({ hasText: "PET/CT" });
    await expect(petCtRow).toBeVisible();
    await expect(petCtRow.getByRole("button", { name: "Compare with another study" })).toHaveCount(0);
  });

  test("deleting a study asks for confirmation and explains the document is preserved", async ({ page }) => {
    await openImagingAndCreateStudy(page);
    await page.getByRole("button", { name: "Delete study" }).click();
    await expect(page.getByRole("heading", { name: "Delete imaging study?" })).toBeVisible();
    await expect(page.getByText("The uploaded source document will remain stored.")).toBeVisible();

    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(page.getByRole("heading", { name: "Delete imaging study?" })).toHaveCount(0);

    await page.getByRole("button", { name: "Delete study" }).click();
    await page.getByRole("alertdialog").getByRole("button", { name: "Delete study" }).click();
    await expect(page.getByRole("heading", { name: "Imaging" })).toBeVisible();
  });

  test("API temporarily unavailable surfaces the existing timeout/retry copy, not a silent hang", async ({ page }) => {
    await page.goto("/workspace");
    await sidebarImagingNav(page).click();

    // Simulate the backend being unreachable for this one request.
    await page.route("**/api/imaging/modalities", (route) => route.abort("connectionrefused"));
    await page.reload();
    await sidebarImagingNav(page).click();

    await expect(page.getByText("Something needs attention")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByRole("button", { name: "Dismiss" })).toBeVisible();
  });
});
