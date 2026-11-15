/*
  The one axios instance the site uses.

  Sessions are HttpOnly cookies (sf_access, 15 min; sf_refresh, 14 days),
  so this file never sees a token. It does three things:

  1. Sends the CSRF token on every POST/PATCH/PUT/DELETE. The token comes
     from GET /api/auth/csrf/ and is kept in memory (the cookie may not be
     readable when the API is on another domain).
  2. On a 401, asks /auth/refresh/ for a new access cookie once and retries.
     Concurrent 401s share one refresh.
  3. Turns the two app-wide 403 codes (email_not_verified, mfa_*) into
     events the app shell reacts to (see AuthContext).
*/
import axios from "axios";

const API_ORIGIN = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

export const api = axios.create({
  baseURL: `${API_ORIGIN}/api`,
  withCredentials: true,
  headers: { Accept: "application/json" },
});

const UNSAFE = new Set(["post", "put", "patch", "delete"]);
// Endpoints whose 401 means "wrong credentials", not "session expired".
const NO_REFRESH = ["/auth/login/", "/auth/mfa/login/", "/auth/refresh/", "/auth/google/", "/auth/logout/"];

let csrfToken = null;
let csrfPromise = null;

export function fetchCsrf(force = false) {
  if (csrfToken && !force) return Promise.resolve(csrfToken);
  if (!csrfPromise) {
    csrfPromise = api
      .get("/auth/csrf/", { _skipAuthRetry: true })
      .then((r) => {
        csrfToken = r.data.csrfToken;
        return csrfToken;
      })
      .finally(() => {
        csrfPromise = null;
      });
  }
  return csrfPromise;
}

let refreshPromise = null;

export function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = api
      .post("/auth/refresh/", {}, { _skipAuthRetry: true })
      .then(() => true)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

// Listeners are set by AuthContext. Kept as plain callbacks, not React state,
// so this module has no React dependency.
const handlers = { sessionEnded: () => {}, emailNotVerified: () => {}, mfa: () => {} };
export function setApiHandlers(next) {
  Object.assign(handlers, next);
}

api.interceptors.request.use(async (config) => {
  if (UNSAFE.has((config.method || "get").toLowerCase())) {
    const token = await fetchCsrf();
    config.headers["X-CSRFToken"] = token;
  }
  return config;
});

function errorCode(data) {
  if (!data || typeof data !== "object") return null;
  const code = Array.isArray(data.code) ? data.code[0] : data.code;
  return typeof code === "string" ? code : null;
}

function isCsrfFailure(error) {
  const detail = error.response?.data?.detail;
  return error.response?.status === 403 && typeof detail === "string" && /^csrf failed/i.test(detail);
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config || {};
    const status = error.response?.status;
    const url = config.url || "";

    // A stale CSRF token (e.g. after signing in): get a fresh one, retry once.
    if (isCsrfFailure(error) && !config._csrfRetried) {
      config._csrfRetried = true;
      await fetchCsrf(true);
      return api(config);
    }

    if (status === 401 && !config._skipAuthRetry && !config._retried && !NO_REFRESH.some((p) => url.startsWith(p))) {
      config._retried = true;
      try {
        await refreshSession();
      } catch {
        handlers.sessionEnded();
        return Promise.reject(error);
      }
      return api(config);
    }

    if (status === 403) {
      const code = errorCode(error.response.data);
      if (code === "email_not_verified") handlers.emailNotVerified();
      if (code === "mfa_required" || code === "mfa_setup_required") handlers.mfa(code);
    }

    return Promise.reject(error);
  },
);

/*
  Error helpers for forms. The API answers {"field": ["message"]} or
  {"detail": "message"}.
*/
export function fieldErrors(error) {
  const data = error?.response?.data;
  if (!data || typeof data !== "object" || Array.isArray(data)) return {};
  const out = {};
  for (const [key, value] of Object.entries(data)) {
    if (key === "detail" || key === "code") continue;
    out[key] = Array.isArray(value) ? value.map(String).join(" ") : typeof value === "string" ? value : null;
  }
  return Object.fromEntries(Object.entries(out).filter(([, v]) => v));
}

export function errorMessage(error, fallback = "Something went wrong. Please try again.") {
  if (!error?.response) return "We couldn't reach SimplyFind. Check your connection and try again.";
  const data = error.response.data;
  if (data && typeof data === "object") {
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.non_field_errors)) return data.non_field_errors.join(" ");
    if (Array.isArray(data)) return data.join(" ");
  }
  if (error.response.status === 429) return "Too many attempts. Wait a minute and try again.";
  return fallback;
}

export function errorCodeOf(error) {
  return errorCode(error?.response?.data);
}

/** Absolute URL for a backend-relative path (media files, CSV exports). */
export function apiUrl(path) {
  if (/^https?:\/\//.test(path)) return path;
  return `${API_ORIGIN}${path.startsWith("/") ? "" : "/"}${path}`;
}
