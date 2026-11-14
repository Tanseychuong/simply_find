import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Spinner } from "./ui";

/** Signed-in pages. Sends visitors to /login?next=<where they were going>. */
export function RequireAuth() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner />;
  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <Outlet />;
}

/** Company dashboard. Signed in but on no team: offer to register a company. */
export function RequireCompany() {
  const { user, loading } = useAuth();
  if (loading) return <Spinner />;
  if (!user?.company) return <Navigate to="/companies/join" replace />;
  return <Outlet />;
}

/** Sign-in and sign-up pages: already signed in, go where you were heading. */
export function GuestOnly() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <Spinner />;
  const params = new URLSearchParams(location.search);
  // ?mfa=1 means the API asked a signed-in team member to sign in again with a code.
  if (user && !params.has("mfa")) return <Navigate to={safeNext(params.get("next"))} replace />;
  return <Outlet />;
}

/**
 * Only same-site paths, so ?next= can't send anyone to another website.
 * Browsers treat "\" like "/", so "/\evil.example" is refused too.
 */
export function safeNext(next, fallback = "/") {
  if (!next || !next.startsWith("/") || next.includes("\\")) return fallback;
  if ([...next].some((ch) => ch.charCodeAt(0) < 32)) return fallback; // tabs/newlines are stripped by URL parsers
  return next.startsWith("//") ? fallback : next;
}
