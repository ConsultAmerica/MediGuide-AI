/**
 * Session token storage and the authenticated fetch every API call uses.
 *
 * The token lives in localStorage so a refresh keeps you signed in. The
 * backend stores only its hash and can revoke it (sign out, expiry), and
 * the token is only ever attached to requests for the MediGuide API origin.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || (process.env.NODE_ENV === "development" ? "http://127.0.0.1:8000" : "");

const TOKEN_KEY = "mediguide.session";
export const SESSION_ENDED_EVENT = "mediguide:session-ended";

export interface AccountUser {
  user_id: string;
  email: string;
  display_name: string;
  is_guest: boolean;
}

export function getSessionToken(): string {
  try {
    return window.localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setSessionToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
    /* storage blocked: the session lasts for this page only */
  }
}

export function clearSessionToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

function targetsApi(input: string): boolean {
  return Boolean(API_BASE_URL) && input.startsWith(API_BASE_URL);
}

/** `fetch` for MediGuide API calls: adds the session token, and announces a
 * rejected session so the workspace can send the user back to sign in. */
export async function apiFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = targetsApi(input) ? getSessionToken() : "";
  const headers = new Headers(init.headers);
  if (token && !headers.has("Authorization")) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(input, { ...init, headers });
  if (response.status === 401 && token) {
    clearSessionToken();
    window.dispatchEvent(new Event(SESSION_ENDED_EVENT));
  }
  return response;
}

export interface SessionResponse {
  token: string;
  user: AccountUser;
}

async function postSession(path: string, body?: object): Promise<SessionResponse> {
  const response = await apiFetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(data?.error?.message || data?.detail || "Something went wrong. Please try again.");
  }
  setSessionToken(data.token);
  return data as SessionResponse;
}

export function signIn(email: string, password: string) {
  return postSession("/api/auth/login", { email, password });
}

/** When called from a guest workspace, the backend upgrades that guest in
 * place, so everything already uploaded stays with the new account. */
export function register(email: string, password: string, displayName = "") {
  return postSession("/api/auth/register", { email, password, display_name: displayName });
}

export function startGuestWorkspace() {
  return postSession("/api/auth/guest");
}

export async function fetchCurrentUser(): Promise<AccountUser | null> {
  if (!getSessionToken()) return null;
  const response = await apiFetch(`${API_BASE_URL}/api/auth/me`);
  if (!response.ok) return null;
  const data = await response.json();
  return data.user as AccountUser;
}

export async function signOut(): Promise<void> {
  try {
    await apiFetch(`${API_BASE_URL}/api/auth/logout`, { method: "POST" });
  } finally {
    clearSessionToken();
  }
}

/** Only same-app workspace paths are honored as a post-sign-in destination. */
export function safeNextPath(raw: string | null): string {
  return raw && raw.startsWith("/workspace") && !raw.startsWith("//") ? raw : "/workspace/home";
}
