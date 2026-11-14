import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchCsrf, refreshSession, setApiHandlers } from "../api/client";
import { authApi } from "../api/auth";

/*
  Who is signed in. `user` is undefined while the first /me is in flight,
  null when signed out, and the /api/auth/me/ object otherwise.

  The access cookie lasts 15 minutes. Public endpoints treat an expired
  cookie as anonymous (no 401), which would quietly show a signed-in
  student "Apply" instead of "Applied". So while signed in, the session
  is refreshed every 12 minutes and when the tab comes back into view.
*/
const AuthContext = createContext(null);
const REFRESH_EVERY_MS = 12 * 60 * 1000;

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [user, setUser] = useState(undefined);
  // App-wide notices raised by the API client (see api/client.js).
  const [emailNotice, setEmailNotice] = useState(false);
  const lastRefresh = useRef(Date.now());

  const loadMe = useCallback(async () => {
    try {
      const me = await authApi.me();
      setUser(me);
      return me;
    } catch {
      setUser(null);
      return null;
    }
  }, []);

  useEffect(() => {
    fetchCsrf().catch(() => {});
    loadMe();
  }, [loadMe]);

  useEffect(() => {
    setApiHandlers({
      sessionEnded: () => setUser(null),
      emailNotVerified: () => setEmailNotice(true),
      mfa: (code) => {
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        navigate(code === "mfa_setup_required" ? `/account/security?setup=1&next=${next}` : `/login?mfa=1&next=${next}`);
      },
    });
  }, [navigate]);

  // Keep the access cookie fresh while signed in.
  const signedIn = Boolean(user);
  useEffect(() => {
    if (!signedIn) return undefined;
    const tick = () => {
      if (Date.now() - lastRefresh.current < REFRESH_EVERY_MS) return;
      lastRefresh.current = Date.now();
      refreshSession().catch(() => setUser(null));
    };
    const id = setInterval(tick, 60 * 1000);
    const onVisible = () => document.visibilityState === "visible" && tick();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [signedIn]);

  /** After any response that set session cookies ({user} from login, register, MFA, Google, claim). */
  const signedInAs = useCallback((nextUser) => {
    lastRefresh.current = Date.now();
    setUser(nextUser);
    setEmailNotice(false);
    // Django may rotate the CSRF token at sign-in.
    fetchCsrf(true).catch(() => {});
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
      fetchCsrf(true).catch(() => {});
      navigate("/");
    }
  }, [navigate]);

  const value = useMemo(
    () => ({
      user,
      loading: user === undefined,
      isCompanyMember: Boolean(user?.company),
      signedInAs,
      reload: loadMe,
      logout,
      emailNotice,
      dismissEmailNotice: () => setEmailNotice(false),
    }),
    [user, signedInAs, loadMe, logout, emailNotice],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
