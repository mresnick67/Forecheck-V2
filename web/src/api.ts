import type { AuthSession, SetupStatus } from "./types";

const API_PREFIX = "/api";
const SESSION_KEY = "forecheck_v2_session";

type RequestInitExt = RequestInit & {
  json?: unknown;
};

function normalizeInit(init?: RequestInitExt): RequestInit {
  const headers = new Headers(init?.headers ?? {});
  const next: RequestInit = {
    method: init?.method ?? "GET",
    headers,
    body: init?.body,
  };

  if (init?.json !== undefined) {
    headers.set("Content-Type", "application/json");
    next.body = JSON.stringify(init.json);
  }

  return next;
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed (${response.status})`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function loadSession(): AuthSession | null {
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    return null;
  }
}

export function saveSession(session: AuthSession): void {
  localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession(): void {
  localStorage.removeItem(SESSION_KEY);
}

export async function publicRequest<T>(path: string, init?: RequestInitExt): Promise<T> {
  const request = normalizeInit(init);
  const response = await fetch(`${API_PREFIX}${path}`, request);
  return parseResponse<T>(response);
}

export async function refreshSession(session: AuthSession): Promise<AuthSession> {
  const response = await fetch(`${API_PREFIX}/auth/refresh`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ refresh_token: session.refreshToken }),
  });

  const payload = await parseResponse<{ access_token: string; refresh_token: string }>(response);
  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
  };
}

export async function authRequest<T>(
  path: string,
  session: AuthSession,
  onSession: (session: AuthSession | null) => void,
  init?: RequestInitExt,
): Promise<T> {
  const request = normalizeInit(init);
  const headers = new Headers(request.headers ?? {});
  headers.set("Authorization", `Bearer ${session.accessToken}`);
  request.headers = headers;

  let response = await fetch(`${API_PREFIX}${path}`, request);

  if (response.status === 401) {
    try {
      const refreshed = await refreshSession(session);
      onSession(refreshed);
      saveSession(refreshed);

      headers.set("Authorization", `Bearer ${refreshed.accessToken}`);
      response = await fetch(`${API_PREFIX}${path}`, request);
    } catch {
      onSession(null);
      clearSession();
      throw new Error("Session expired. Please log in again.");
    }
  }

  return parseResponse<T>(response);
}

export async function fetchSetupStatus(): Promise<SetupStatus> {
  return publicRequest<SetupStatus>("/setup/status");
}

export async function bootstrapOwner(payload: {
  username: string;
  email: string;
  password: string;
  display_name?: string;
}): Promise<void> {
  await publicRequest("/setup/bootstrap", {
    method: "POST",
    json: payload,
  });
}

export async function login(username: string, password: string): Promise<AuthSession> {
  const body = new URLSearchParams({ username, password });
  const response = await fetch(`${API_PREFIX}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
  });

  const payload = await parseResponse<{ access_token: string; refresh_token: string }>(response);

  return {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
  };
}
