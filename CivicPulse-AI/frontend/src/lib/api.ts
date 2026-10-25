const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Access token lives in memory only (never localStorage — XSS hygiene). The
// refresh token is an httpOnly cookie the browser sends automatically.
let accessToken: string | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}
export function getAccessToken(): string | null {
  return accessToken;
}

export class ApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

type Opts = { method?: string; body?: unknown; headers?: Record<string, string> };

async function request<T>(path: string, opts: Opts = {}, allowRetry = true): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const res = await fetch(`${API}/api/v1${path}`, {
    method: opts.method ?? "GET",
    headers,
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    credentials: "include",
  });

  // One transparent refresh-and-retry on an expired access token.
  if (res.status === 401 && allowRetry) {
    const refreshed = await tryRefresh();
    if (refreshed) return request<T>(path, opts, false);
  }

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    const d = detail?.detail ?? {};
    throw new ApiError(res.status, d.code ?? "error", d.message ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function tryRefresh(): Promise<boolean> {
  const res = await fetch(`${API}/api/v1/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  if (!res.ok) return false;
  const data = await res.json();
  accessToken = data.access_token;
  return true;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body }),
  patch: <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body }),
};

// Raw PUT straight to object storage (presigned URL) — no auth header, no /api prefix.
export async function uploadToStorage(url: string, file: File): Promise<void> {
  const res = await fetch(url, {
    method: "PUT",
    body: file,
    headers: { "Content-Type": file.type },
  });
  if (!res.ok) throw new Error(`upload failed: ${res.status}`);
}
