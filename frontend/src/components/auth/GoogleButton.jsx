import { useEffect, useRef, useState } from "react";

/*
  "Sign in with Google" (Google Identity Services). Hidden unless
  VITE_GOOGLE_CLIENT_ID is set, the same client ID as the backend's
  GOOGLE_CLIENT_ID. `onCredential(idToken)` receives the ID token for
  POST /api/auth/google/.
*/
const CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID || "";
const SCRIPT_SRC = "https://accounts.google.com/gsi/client";
let scriptPromise = null;

function loadScript() {
  if (window.google?.accounts?.id) return Promise.resolve();
  if (!scriptPromise) {
    scriptPromise = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = SCRIPT_SRC;
      s.async = true;
      s.onload = resolve;
      s.onerror = () => {
        scriptPromise = null;
        reject(new Error("Google sign-in could not load"));
      };
      document.head.appendChild(s);
    });
  }
  return scriptPromise;
}

export const googleEnabled = Boolean(CLIENT_ID);

export default function GoogleButton({ onCredential, text = "continue_with" }) {
  const ref = useRef(null);
  const callbackRef = useRef(onCredential);
  callbackRef.current = onCredential;
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!CLIENT_ID) return undefined;
    let cancelled = false;
    loadScript()
      .then(() => {
        if (cancelled || !ref.current) return;
        window.google.accounts.id.initialize({
          client_id: CLIENT_ID,
          callback: (response) => callbackRef.current(response.credential),
        });
        window.google.accounts.id.renderButton(ref.current, {
          theme: document.documentElement.classList.contains("dark") ? "filled_black" : "outline",
          size: "large",
          text,
          shape: "rectangular",
          width: Math.min(ref.current.offsetWidth || 360, 400),
        });
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [text]);

  if (!CLIENT_ID) return null;
  if (failed) return <p className="text-center text-xs text-muted">Google sign-in isn't available right now.</p>;
  return <div ref={ref} className="flex min-h-11 w-full justify-center" />;
}
