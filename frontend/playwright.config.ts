import { defineConfig } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { E2E_BACKEND_PORT, E2E_FRONTEND_PORT, E2E_STORAGE_STATE } from "./e2e/auth-paths";

const BACKEND_PORT = E2E_BACKEND_PORT;
const FRONTEND_PORT = E2E_FRONTEND_PORT;
const REPO_ROOT = path.resolve(__dirname, "..");
const SCRATCH_DIR = path.join(__dirname, "e2e", ".scratch");

// The backend's webServer entry below starts before any spec file's
// test.beforeAll runs, and SQLite (unlike most drivers) cannot create its
// own database file inside a directory that doesn't exist yet — on a truly
// fresh checkout (no prior .scratch/ from an earlier run), that failure was
// silently swallowed by the app's own startup handler, leaving every DB
// table missing and every imaging/timeline request fail with a bare
// "Failed to fetch" in the browser. Creating it here, before webServer
// spawns, is what actually prevents that.
fs.mkdirSync(SCRATCH_DIR, { recursive: true });

const backendEnv = {
  ...process.env,
  DATABASE_URL: `sqlite:///${path.join(SCRATCH_DIR, "e2e.db").replace(/\\/g, "/")}`,
  FRONTEND_ORIGINS: `http://localhost:${FRONTEND_PORT}`,
  DOC_INTEL_TEMP_DIR: path.join(SCRATCH_DIR, "document_intelligence"),
  IMAGING_TEMP_DIR: path.join(SCRATCH_DIR, "imaging"),
  MED_WORKSPACE_TEMP_DIR: path.join(SCRATCH_DIR, "medication_workspace"),
  // Fast, deterministic failure paths for the failure-path spec — a real
  // Ollama endpoint is not expected to be reachable in CI, so these knobs
  // (added in the reliability sprint) bound how long a "processing" state
  // is visible before the UI's own timeout/retry copy takes over.
  PROCESSING_RETRY_ATTEMPTS: "1",
  PROCESSING_RETRY_BACKOFF_SECONDS: "0",
  OLLAMA_TIMEOUT_SECONDS: "2",
};

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: "list",
  use: {
    // "localhost", not "127.0.0.1": Next 16's dev server treats the two as
    // different origins and returns 403 on its own static chunks/HMR
    // socket for the mismatched one (allowedDevOrigins), silently breaking
    // hydration — the page paints but click handlers never attach. This
    // bit only shows up under automation; a human browsing localhost:3000
    // never triggers it.
    baseURL: `http://localhost:${FRONTEND_PORT}`,
    trace: "retain-on-failure",
    viewport: { width: 1280, height: 800 },
  },
  projects: [
    { name: "setup", testMatch: /auth.setup.ts/ },
    {
      name: "workspace",
      dependencies: ["setup"],
      testIgnore: /auth.setup.ts/,
      use: { storageState: E2E_STORAGE_STATE },
    },
  ],
  webServer: [
    {
      command: `"${path.join(REPO_ROOT, ".venv", "Scripts", "python.exe")}" -m uvicorn api:app --host 127.0.0.1 --port ${BACKEND_PORT}`,
      cwd: REPO_ROOT,
      port: BACKEND_PORT,
      env: backendEnv,
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      command: `npx next dev -p ${FRONTEND_PORT} -H localhost`,
      cwd: __dirname,
      port: FRONTEND_PORT,
      env: {
        ...process.env,
        NEXT_PUBLIC_API_URL: `http://127.0.0.1:${BACKEND_PORT}`,
        // Small page size so timeline-pagination.spec.ts can exercise
        // "Load more" without seeding 25+ records through real UI flows.
        NEXT_PUBLIC_TIMELINE_PAGE_SIZE: "3",
      },
      reuseExistingServer: false,
      timeout: 60_000,
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});
