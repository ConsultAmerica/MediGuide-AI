import path from "node:path";

export const E2E_BACKEND_PORT = 8199;
export const E2E_FRONTEND_PORT = 3199;
export const E2E_BACKEND_URL = `http://127.0.0.1:${E2E_BACKEND_PORT}`;
export const E2E_FRONTEND_URL = `http://localhost:${E2E_FRONTEND_PORT}`;

const SCRATCH_DIR = path.join(__dirname, ".scratch");
export const E2E_STORAGE_STATE = path.join(SCRATCH_DIR, "guest-storage-state.json");
export const E2E_OWNER_FILE = path.join(SCRATCH_DIR, "guest-user-id.txt");
