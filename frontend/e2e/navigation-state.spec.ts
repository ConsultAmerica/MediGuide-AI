import fs from "node:fs";
import path from "node:path";
import { expect, test, type APIRequestContext } from "@playwright/test";
import { E2E_BACKEND_URL, E2E_STORAGE_STATE } from "./auth-paths";
import { generateLabReportPdf, generateReportPdf } from "./helpers";

const FIXTURES_DIR = path.join(__dirname, ".scratch", "fixtures");

// Records are seeded through the real API as the suite guest, then the
// browser checks that what's on screen lives in the URL. Triglycerides and
// ALT are used because no other spec touches them (the scratch DB is shared,
// and synthetic-demo.spec.ts counts Hemoglobin A1C points exactly).

function authHeaders() {
  const state = JSON.parse(fs.readFileSync(E2E_STORAGE_STATE, "utf8"));
  return { Authorization: `Bearer ${state.origins[0].localStorage[0].value}` };
}

async function seedConfirmedLab(
  request: APIRequestContext,
  name: string,
  opts: { testName: string; value: string; unit: string; referenceRange: string; collectionDate: string },
) {
  const filePath = path.join(FIXTURES_DIR, name);
  generateLabReportPdf(filePath, opts);
  const headers = authHeaders();
  const upload = await request.post(`${E2E_BACKEND_URL}/api/documents/v2/upload`, {
    headers,
    multipart: { file: { name, mimeType: "application/pdf", buffer: fs.readFileSync(filePath) } },
  });
  const { document_id: documentId } = await upload.json();
  const state = await (await request.post(`${E2E_BACKEND_URL}/api/documents/v2/${documentId}/process`, { headers })).json();
  const confirmed = await request.post(`${E2E_BACKEND_URL}/api/documents/v2/${documentId}/confirm`, {
    headers,
    data: { fields: state.fields, reviewed_names_values_units_dates: true },
  });
  expect(confirmed.ok()).toBeTruthy();
  return documentId as string;
}

async function seedVerifiedStudy(request: APIRequestContext, bodyRegion: string, studyDate: string) {
  const headers = authHeaders();
  const study = await (
    await request.post(`${E2E_BACKEND_URL}/api/imaging/studies`, {
      headers,
      data: { modality: "mri", body_region: bodyRegion, study_date: studyDate },
    })
  ).json();
  const reportPath = path.join(FIXTURES_DIR, `nav-${study.study_id}.pdf`);
  generateReportPdf(reportPath, { exam: `MRI ${bodyRegion}`, findings: "No acute abnormality.", impression: "No acute abnormality." });
  await request.post(`${E2E_BACKEND_URL}/api/imaging/studies/${study.study_id}/report`, {
    headers,
    multipart: { file: { name: "report.pdf", mimeType: "application/pdf", buffer: fs.readFileSync(reportPath) } },
  });
  await request.post(`${E2E_BACKEND_URL}/api/imaging/studies/${study.study_id}/report/confirm`, {
    headers,
    data: { reviewed: true, sections: [] },
  });
  return study.study_id as string;
}

test.beforeAll(() => {
  fs.mkdirSync(FIXTURES_DIR, { recursive: true });
});

test.describe("Navigation state survives refresh and Back/Forward", () => {
  test("Labs: selected test and open result live in the URL", async ({ page, request }) => {
    await seedConfirmedLab(request, "nav-trig.pdf", {
      testName: "Triglycerides", value: "142", unit: "mg/dL", referenceRange: "0-150", collectionDate: "2026-03-04",
    });
    await seedConfirmedLab(request, "nav-alt.pdf", {
      testName: "ALT", value: "31", unit: "U/L", referenceRange: "7-56", collectionDate: "2026-03-05",
    });

    await page.goto("/workspace/labs?test=triglycerides");
    const testSelector = page.getByLabel("Test selector");
    await expect(testSelector).toHaveValue("triglycerides");

    // Opening a result records it; a refresh reopens the same one.
    await page.locator("tbody tr").filter({ hasText: "142" }).first().click();
    await expect(page).toHaveURL(/\/workspace\/labs\?test=triglycerides&point=/);
    await page.reload();
    await expect(page.locator(".lab-result-drawer-backdrop")).toBeVisible();

    // Back closes the result instead of leaving Labs.
    await page.goBack();
    await expect(page).toHaveURL(/\/workspace\/labs\?test=triglycerides$/);
    await expect(page.locator(".lab-result-drawer-backdrop")).toHaveCount(0);

    // Switching tests is a history step too.
    await testSelector.selectOption("alt");
    await expect(page).toHaveURL(/\?test=alt$/);
    await expect(page.locator("tbody tr").filter({ hasText: "31" }).first()).toBeVisible();
    await page.goBack();
    await expect(page).toHaveURL(/\?test=triglycerides$/);
    await expect(testSelector).toHaveValue("triglycerides");
  });

  test("Imaging: list, study and tab survive refresh, Back and Forward", async ({ page, request }) => {
    const region = `Nav knee ${Date.now()}`;
    const studyId = await seedVerifiedStudy(request, region, "2026-02-01");

    await page.goto("/workspace/imaging");
    await page.locator(".imaging-modality-card").filter({ hasText: "MRI" }).click();
    await expect(page).toHaveURL(/\/workspace\/imaging\?modality=mri$/);
    await expect(page.getByRole("heading", { name: "MRI Studies" })).toBeVisible();

    await page.getByText(region).first().click();
    await expect(page).toHaveURL(new RegExp(`/workspace/imaging/${studyId}`));
    await expect(page.locator(".imaging-study-meta")).toBeVisible();

    const tabs = page.getByRole("navigation", { name: "Study sections" });
    await tabs.getByRole("button", { name: "Source" }).click();
    await expect(page).toHaveURL(/tab=source/);
    await page.reload();
    await expect(tabs.getByRole("button", { name: "Source" })).toHaveClass(/active/);

    // Back returns to the list it came from, not out of Imaging.
    await page.goBack();
    await expect(page).toHaveURL(/\/workspace\/imaging\?modality=mri$/);
    await expect(page.getByRole("heading", { name: "MRI Studies" })).toBeVisible();
    await page.goForward();
    await expect(page.locator(".imaging-study-meta")).toBeVisible();

    // The older ?openStudy= link still lands on the study.
    await page.goto(`/workspace/imaging?openStudy=${studyId}`);
    await expect(page).toHaveURL(new RegExp(`/workspace/imaging/${studyId}$`));
    await expect(page.locator(".imaging-study-meta")).toBeVisible();
  });

  test("Search: Enter opens the highlighted result, at its exact field", async ({ page, request }) => {
    // A newer imaging study matching the same word comes first in the API's
    // date order but second on screen (lab results are grouped first); Enter
    // must open the highlighted lab result, not the API's first hit.
    const labDocumentId = await seedConfirmedLab(request, "nav-search-trig.pdf", {
      testName: "Triglycerides", value: "160", unit: "mg/dL", referenceRange: "0-150", collectionDate: "2026-01-10",
    });
    await seedVerifiedStudy(request, "Triglycerides follow-up", "2030-01-01");

    await page.goto("/workspace/home");
    await expect(page.locator(".app-header")).toBeVisible();
    await page.keyboard.press("Control+k");
    await page.getByRole("combobox", { name: "Search your health information" }).fill("triglycerides");
    const highlighted = page.locator('[role="option"][aria-selected="true"]');
    await expect(highlighted).toContainText("Lab Report");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(new RegExp(`/workspace/documents/[a-f0-9]+\\?page=1&field=`));
    expect(labDocumentId).toBeTruthy();
  });

  test("Search: Try again really retries", async ({ page }) => {
    let calls = 0;
    await page.route("**/api/search?**", async (route) => {
      calls += 1;
      if (calls === 1) await route.fulfill({ status: 503, json: { error: { code: "X", message: "Search is down for a moment.", retryable: true } } });
      else await route.continue();
    });

    await page.goto("/workspace/home");
    await expect(page.locator(".app-header")).toBeVisible();
    await page.keyboard.press("Control+k");
    await page.getByRole("combobox", { name: "Search your health information" }).fill("triglycerides");
    await expect(page.getByText("Search is down for a moment.")).toBeVisible();
    await page.getByRole("button", { name: "Try again" }).click();
    // A completed search replaces the error (results or "0 results"; this
    // guest may own nothing matching when the spec runs alone).
    await expect(page.getByRole("status").filter({ hasText: /results? found/ })).toBeVisible();
    await expect(page.getByText("Search is down for a moment.")).toHaveCount(0);
    expect(calls).toBe(2);
  });
});
