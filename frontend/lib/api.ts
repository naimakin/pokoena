const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Endpoints that are inherently about establishing/renewing a session
// themselves — a 401 from one of these must never trigger the refresh-and-
// retry logic below (that would either loop or paper over a genuine bad
// login attempt as if it were an expired session).
const SESSION_ENDPOINTS = ["/auth/login", "/auth/refresh", "/platform-auth/login", "/platform-auth/refresh"];

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function isPlatformArea(): boolean {
  return typeof window !== "undefined" && window.location.pathname.startsWith("/platform-admin");
}

async function tryRefreshSession(): Promise<boolean> {
  const refreshPath = isPlatformArea() ? "/platform-auth/refresh" : "/auth/refresh";
  try {
    const response = await fetch(`${API_URL}${refreshPath}`, { method: "POST", credentials: "include" });
    return response.ok;
  } catch {
    return false;
  }
}

async function request<T>(path: string, options: RequestInit = {}, isRetry = false): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  // A 15-minute access token expiring mid-session shouldn't surface as a raw
  // error on whatever the person happened to be doing — try once, silently,
  // to renew it from the (longer-lived) refresh cookie before giving up.
  if (response.status === 401 && !isRetry && !SESSION_ENDPOINTS.includes(path)) {
    if (await tryRefreshSession()) {
      return request<T>(path, options, true);
    }
    // Refresh cookie is gone or invalid too — the session is genuinely over.
    // A toast on a page nobody can act on isn't useful; send them back to
    // sign in instead of leaving every subsequent action failing silently.
    if (typeof window !== "undefined") {
      window.location.href = isPlatformArea() ? "/platform-admin/login" : "/login";
    }
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // no JSON body on this error response — fall back to statusText
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// Multipart upload — deliberately bypasses `request()`'s JSON Content-Type
// header (the browser needs to set its own multipart boundary) but reuses
// the same 401-refresh-and-retry / error-shape handling via a raw fetch.
async function requestFile<T>(path: string, formData: FormData, isRetry = false): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  if (response.status === 401 && !isRetry) {
    if (await tryRefreshSession()) {
      return requestFile<T>(path, formData, true);
    }
    if (typeof window !== "undefined") {
      window.location.href = isPlatformArea() ? "/platform-admin/login" : "/login";
    }
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // no JSON body on this error response — fall back to statusText
    }
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  postFile: <T>(path: string, formData: FormData) => requestFile<T>(path, formData),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
