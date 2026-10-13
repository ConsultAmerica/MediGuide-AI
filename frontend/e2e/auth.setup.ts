import fs from "node:fs";
import { test as setup, expect } from "@playwright/test";
import { E2E_BACKEND_URL, E2E_FRONTEND_URL, E2E_OWNER_FILE, E2E_STORAGE_STATE } from "./auth-paths";

// Every record API requires a signed-in owner, so the suite runs as one
// guest workspace created through the real auth API. Specs share it the
// same way they already share the scratch database.
setup("create a guest workspace for the suite", async ({ request }) => {
  const response = await request.post(`${E2E_BACKEND_URL}/api/auth/guest`);
  expect(response.ok()).toBeTruthy();
  const { token, user } = await response.json();

  fs.writeFileSync(
    E2E_STORAGE_STATE,
    JSON.stringify({
      cookies: [],
      origins: [{ origin: E2E_FRONTEND_URL, localStorage: [{ name: "mediguide.session", value: token }] }],
    }),
  );
  // Seed scripts write rows directly, so they need the owner's id.
  fs.writeFileSync(E2E_OWNER_FILE, user.user_id);
});
