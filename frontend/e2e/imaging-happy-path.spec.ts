import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import { generateReportPdf, seedDemoImaging, sidebarImagingNav } from "./helpers";

const FIXTURES_DIR = path.join(__dirname, ".scratch", "fixtures");

test.beforeAll(() => {
  fs.mkdirSync(FIXTURES_DIR, { recursive: true });
  seedDemoImaging(); // gives History/Compare a second (and third) verified MRI study
});

test.describe("Imaging — canonical happy path", () => {
  test("open Imaging, add a study, review, confirm, compare, and explain a term", async ({ page }) => {
    // Unique per run: other specs share this scratch database and also create
    // undated MRI studies, so "Undated" alone can pick the wrong one.
    const BODY_REGION = `Right knee ${Date.now()}`;
    const reportPath = path.join(FIXTURES_DIR, "happy-path-report.pdf");
    generateReportPdf(reportPath, {
      exam: "MRI Right Knee",
      clinicalHistory: "Follow-up right knee pain.",
      technique: "Standard MRI knee protocol.",
      findings: "No acute fracture. New joint effusion is noted.",
      impression: "New joint effusion.",
    });

    await page.goto("/workspace");
    // Wait for hydration to finish before the first interaction — Next 16's
    // streaming hydration can paint the sidebar before its click handlers
    // are attached.
    await expect(sidebarImagingNav(page)).toBeEnabled();

    // Open Imaging
    await sidebarImagingNav(page).click();
    await expect(page.getByRole("heading", { name: "Imaging" })).toBeVisible();

    // Select MRI
    await page.locator(".imaging-modality-card").filter({ hasText: "MRI" }).click();
    await expect(page.getByRole("heading", { name: "MRI Studies" })).toBeVisible();
    // The sidebar's "Imaging" nav only (re)mounts the workspace on a real
    // view change — it's a no-op once already inside Imaging, since the
    // sub-view (landing/list/detail/...) is internal state. Use the
    // in-view "← Imaging" back button to return to the modality browser.
    await page.locator(".imaging-back").click();

    // Add synthetic MRI study
    await page.getByRole("button", { name: "Add imaging study" }).click();
    await page.locator(".imaging-add-form select").selectOption("mri");
    await page.getByPlaceholder("e.g. Right knee").fill(BODY_REGION);
    await page.getByRole("button", { name: "Create study" }).click();
    await expect(page.locator(".imaging-study-meta")).toContainText("MRI");

    // Upload synthetic imaging report
    await page.locator(".imaging-upload-label input[type=file]").setInputFiles(reportPath);

    // Wait for extraction (processing checklist appears, then the report panel)
    await expect(page.getByText("Processing imaging report")).toBeVisible();
    await expect(page.getByText(/sections reviewed/)).toBeVisible({ timeout: 30_000 });

    // Review report sections — focusing each textarea marks it reviewed
    const textareas = page.locator(".imaging-section-block textarea");
    const sectionCount = await textareas.count();
    for (let i = 0; i < sectionCount; i += 1) {
      await textareas.nth(i).click();
    }
    await expect(page.getByText(`${sectionCount} of ${sectionCount} sections reviewed`)).toBeVisible();

    // Edit one section
    const findingsBox = page.getByLabel("Findings");
    await findingsBox.fill("No acute fracture. New joint effusion is noted. Corrected by reviewer.");
    await expect(page.getByText("Original extraction")).toBeVisible();

    // Confirm sections
    await page.getByRole("button", { name: "Confirm reviewed sections" }).click();
    await expect(page.locator(".lab-verified")).toContainText("Verified");

    // View source page
    // Opens the study's Source tab on that page; the preview is fetched with
    // the session token (a bare <img src> would be rejected as unauthenticated).
    await page.getByRole("button", { name: "View source page" }).first().click();
    await expect(page.locator(".imaging-source-banner")).toContainText("Opening the correct report page");
    await expect(page.getByRole("img", { name: "Page 1", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Back", exact: true }).click();

    // Return to Imaging history
    await page.getByRole("button", { name: "View history" }).click();
    await expect(page.getByRole("heading", { name: "Imaging History" })).toBeVisible();

    // Select a second (seeded) MRI study and compare. History groups by
    // year with the undated (freshly created) study sorting first, so the
    // *last* "Compare with another study" button belongs to an older,
    // seeded MRI study — distinct from the study we're about to pick as
    // the "Later report" below.
    const compareButtons = page.getByRole("button", { name: "Compare with another study" });
    await expect(compareButtons.last()).toBeVisible();
    await compareButtons.last().click();
    await expect(page.getByRole("heading", { name: "Compare Imaging Reports" })).toBeVisible();

    // Later report is the freshly created + confirmed study, picked by its
    // unique body region. selectOption's {label} match requires an exact
    // string (no regex), so the option's real text is read first.
    const laterSelect = page.locator(".imaging-compare-picker select").nth(1);
    const laterLabel = await laterSelect.locator("option", { hasText: BODY_REGION }).first().textContent();
    await laterSelect.selectOption({ label: (laterLabel ?? "").trim() });
    await page.getByRole("button", { name: "What changed?" }).click();
    await expect(page.locator(".imaging-compare-section").first()).toBeVisible({ timeout: 15_000 });

    // Inspect "Newly mentioned" on the Findings comparison specifically —
    // the edited/new findings text must show up as newly mentioned, not
    // just the static column header.
    const findingsCompareSection = page
      .locator(".imaging-compare-section")
      .filter({ has: page.getByRole("heading", { name: "Findings" }) });
    await expect(findingsCompareSection).toContainText("New joint effusion");

    // Open source evidence from a comparison row
    await findingsCompareSection.getByRole("button", { name: "View later source" }).click();
    await expect(page.locator(".imaging-study-meta")).toBeVisible();
    // Report-panel actions live on the study's Report tab.
    await page.getByRole("navigation", { name: "Study sections" }).getByRole("button", { name: "Report" }).click();

    // Open terminology explanation
    await page.getByRole("button", { name: "Understand terminology" }).first().click();
    await expect(page.getByRole("heading", { name: "Understand this term" })).toBeVisible();
    await page.getByPlaceholder("e.g. joint effusion").fill("joint effusion");
    await page.getByRole("button", { name: "Explain" }).click();
    // Whether or not the local approved knowledge base finds evidence for
    // this term, an answer (real explanation, or the honest "not enough
    // approved information" degradation) must appear — never a hang.
    await expect(page.locator(".imaging-term-answer-text")).toBeVisible({ timeout: 20_000 });
  });
});
