import { execFileSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";
import { expect, type Page } from "@playwright/test";
import { E2E_OWNER_FILE } from "./auth-paths";

/** The sidebar's "Imaging" nav button — scoped to <aside> because several
 * in-view "back to Imaging" buttons also render the bare text "Imaging". */
export function sidebarImagingNav(page: Page) {
  return page.locator("aside").getByRole("button", { name: "Imaging", exact: true });
}

/** Confirms every imaging report section still awaiting a decision, one at
 * a time (each decision is saved before the next button is clicked). */
export async function confirmRemainingImagingSections(page: Page) {
  const confirmButtons = page.locator(".imaging-section-block").getByRole("button", { name: "Confirm", exact: true });
  for (let guard = 0; guard < 20; guard += 1) {
    const remaining = await confirmButtons.count();
    if (remaining === 0) return;
    await confirmButtons.first().click();
    await expect(confirmButtons).toHaveCount(remaining - 1);
  }
}

const REPO_ROOT = path.resolve(__dirname, "..", "..");
const SCRATCH_DIR = path.join(__dirname, ".scratch");
const PYTHON = path.join(REPO_ROOT, ".venv", "Scripts", "python.exe");

function scratchEnv() {
  return {
    ...process.env,
    // Seed scripts own their rows as the suite guest (see auth.setup.ts).
    MEDIGUIDE_SEED_OWNER_ID: fs.existsSync(E2E_OWNER_FILE) ? fs.readFileSync(E2E_OWNER_FILE, "utf8").trim() : "",
    DATABASE_URL: `sqlite:///${path.join(SCRATCH_DIR, "e2e.db").replace(/\\/g, "/")}`,
    PYTHONPATH: REPO_ROOT,
  };
}

export function generateReportPdf(
  outputPath: string,
  opts: {
    exam?: string;
    clinicalHistory?: string;
    technique?: string;
    findings?: string;
    impression?: string;
    invalid?: boolean;
    noRecognizedHeaders?: boolean;
  } = {},
): void {
  const args = [
    path.join(REPO_ROOT, "scripts", "generate_synthetic_imaging_report.py"),
    "--output",
    outputPath,
  ];
  if (opts.exam) args.push("--exam", opts.exam);
  if (opts.clinicalHistory) args.push("--clinical-history", opts.clinicalHistory);
  if (opts.technique) args.push("--technique", opts.technique);
  if (opts.findings) args.push("--findings", opts.findings);
  if (opts.impression) args.push("--impression", opts.impression);
  if (opts.invalid) args.push("--invalid");
  if (opts.noRecognizedHeaders) args.push("--no-recognized-headers");

  execFileSync(PYTHON, args, { cwd: REPO_ROOT, env: scratchEnv() });
}

export function generateLabReportPdf(
  outputPath: string,
  opts: {
    testName?: string;
    value?: string;
    unit?: string;
    referenceRange?: string;
    collectionDate?: string;
  } = {},
): void {
  const args = [
    path.join(REPO_ROOT, "scripts", "generate_synthetic_lab_report.py"),
    "--output",
    outputPath,
  ];
  if (opts.testName) args.push("--test-name", opts.testName);
  if (opts.value) args.push("--value", opts.value);
  if (opts.unit) args.push("--unit", opts.unit);
  if (opts.referenceRange) args.push("--reference-range", opts.referenceRange);
  if (opts.collectionDate) args.push("--collection-date", opts.collectionDate);

  execFileSync(PYTHON, args, { cwd: REPO_ROOT, env: scratchEnv() });
}

export function seedDemoImaging(): void {
  execFileSync(PYTHON, [path.join(REPO_ROOT, "scripts", "seed_demo_imaging.py")], {
    cwd: REPO_ROOT,
    env: scratchEnv(),
  });
}

export function seedPaginationImaging(token: string, count = 4): void {
  execFileSync(
    PYTHON,
    [path.join(REPO_ROOT, "scripts", "seed_e2e_pagination_imaging.py"), "--token", token, "--count", String(count)],
    { cwd: REPO_ROOT, env: scratchEnv() },
  );
}
