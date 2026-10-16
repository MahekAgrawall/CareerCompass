/**
 * Thin fetch wrapper around the CareerCompass API.
 *
 * - Resolves the base URL from `VITE_API_BASE_URL` (defaults to the local dev server).
 * - Attaches the JWT bearer token from a pluggable getter (wired up by AuthContext).
 * - Normalises FastAPI error payloads (`{ detail: ... }`) into `ApiError`.
 * - Exposes a streaming helper for the copilot's chunked text responses.
 */

const RAW_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export const API_BASE_URL = RAW_BASE_URL.replace(/\/+$/, "");

let tokenGetter: () => string | null = () => null;

/** Registered once by AuthContext so every request reads the latest token. */
export function setTokenGetter(getter: () => string | null): void {
  tokenGetter = getter;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function authHeaders(): Record<string, string> {
  const token = tokenGetter();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function parseError(res: Response): Promise<string> {
  try {
    const data: unknown = await res.json();
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail: unknown }).detail;
      if (typeof detail === "string") return detail;
      if (Array.isArray(detail)) {
        return detail
          .map((item) =>
            item && typeof item === "object" && "msg" in item
              ? String((item as { msg: unknown }).msg)
              : String(item),
          )
          .join(", ");
      }
    }
  } catch {
    // Fall through to the status text below.
  }
  return res.statusText || `Request failed (${res.status})`;
}

export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(options.headers ?? {}),
    },
  });

  if (!res.ok) {
    throw new ApiError(res.status, await parseError(res));
  }
  if (res.status === 204) {
    return undefined as T;
  }
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T>(path: string, options?: RequestInit) => apiRequest<T>(path, { ...options }),
  post: <T>(path: string, body?: unknown, options?: RequestInit) =>
    apiRequest<T>(path, { method: "POST", body: JSON.stringify(body ?? {}), ...options }),
  put: <T>(path: string, body?: unknown, options?: RequestInit) =>
    apiRequest<T>(path, { method: "PUT", body: JSON.stringify(body ?? {}), ...options }),
  patch: <T>(path: string, body?: unknown, options?: RequestInit) =>
    apiRequest<T>(path, { method: "PATCH", body: JSON.stringify(body ?? {}), ...options }),
  del: <T>(path: string, options?: RequestInit) => apiRequest<T>(path, { method: "DELETE", ...options }),
};

/** True when a request failed because we aborted it (e.g. it timed out). */
export function isAbortError(error: unknown): boolean {
  if (error instanceof DOMException) {
    return error.name === "AbortError" || error.name === "TimeoutError";
  }
  return error instanceof Error && error.name === "AbortError";
}

/**
 * Builds an AbortSignal that fires after `timeoutMs` and a `cancel()` for cleanup.
 * Lets AI-backed calls surface a friendly error instead of spinning forever.
 */
export function withTimeout(timeoutMs: number): { signal: AbortSignal; cancel: () => void } {
  const controller = new AbortController();
  const timer = window.setTimeout(
    () => controller.abort(new DOMException("Request timed out", "TimeoutError")),
    timeoutMs,
  );
  return {
    signal: controller.signal,
    cancel: () => window.clearTimeout(timer),
  };
}

/**
 * Streams a plain-text response (the copilot), invoking `onChunk` as text arrives.
 * Returns when the server closes the stream.
 */
export async function apiStream(
  path: string,
  body: unknown,
  onChunk: (text: string) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    throw new ApiError(res.status, await parseError(res));
  }

  const reader = res.body?.getReader();
  if (!reader) {
    throw new ApiError(500, "Streaming is not supported in this browser.");
  }

  const decoder = new TextDecoder();
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) onChunk(decoder.decode(value, { stream: true }));
  }
}
