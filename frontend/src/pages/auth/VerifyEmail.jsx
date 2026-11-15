import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CheckCircle2, MailWarning } from "lucide-react";
import { authApi } from "../../api/auth";
import { errorMessage } from "../../api/client";
import AuthCard from "../../components/auth/AuthCard";
import { Button, ButtonLink, Spinner } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { useTitle } from "../../lib/hooks";

/* Opened from the confirmation email: /verify-email?token=... */
export default function VerifyEmail() {
  useTitle("Confirm your email");
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const { user, reload } = useAuth();
  const [state, setState] = useState({ status: token ? "checking" : "error", message: token ? null : "This link is incomplete." });
  const sent = useRef(false); // StrictMode runs effects twice in development; send the token once
  const [resend, setResend] = useState({ busy: false, message: null });

  useEffect(() => {
    if (!token || sent.current) return;
    sent.current = true;
    authApi
      .verifyEmail(token)
      .then((data) => {
        setState({ status: "done", message: data.detail });
        reload();
      })
      .catch((err) => setState({ status: "error", message: errorMessage(err) }));
  }, [token, reload]);

  async function resendLink() {
    setResend({ busy: true, message: null });
    try {
      setResend({ busy: false, message: (await authApi.resendVerification()).detail });
    } catch (err) {
      setResend({ busy: false, message: errorMessage(err) });
    }
  }

  if (state.status === "checking") return <Spinner label="Confirming your email" />;

  if (state.status === "done") {
    return (
      <AuthCard title="Email confirmed">
        <div className="space-y-4 text-center">
          <CheckCircle2 className="mx-auto size-10 text-success" aria-hidden />
          <p className="text-sm">{state.message} You can now apply for roles.</p>
          <ButtonLink to={user ? "/profile" : "/login"} className="w-full">{user ? "Continue to your profile" : "Sign in"}</ButtonLink>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="We couldn't confirm your email">
      <div className="space-y-4 text-center">
        <MailWarning className="mx-auto size-10 text-danger" aria-hidden />
        <p className="text-sm">{state.message}</p>
        {user && !user.email_verified ? (
          <>
            <Button onClick={resendLink} loading={resend.busy} className="w-full">Send me a new link</Button>
            {resend.message && <p className="text-sm text-muted">{resend.message}</p>}
          </>
        ) : user?.email_verified ? (
          <ButtonLink to="/profile" className="w-full">Your email is already confirmed</ButtonLink>
        ) : (
          <ButtonLink to={`/login?next=${encodeURIComponent("/account/security")}`} className="w-full">Sign in to get a new link</ButtonLink>
        )}
      </div>
    </AuthCard>
  );
}
