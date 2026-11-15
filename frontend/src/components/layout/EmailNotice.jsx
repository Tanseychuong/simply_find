import { useState } from "react";
import { MailCheck, X } from "lucide-react";
import { authApi } from "../../api/auth";
import { errorMessage } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import { Button, Container } from "../ui";

/*
  Shown when the API refuses something with code email_not_verified
  (applying, creating a company), and on every page while a signed-in
  user's email is unconfirmed.
*/
export default function EmailNotice() {
  const { user, emailNotice, dismissEmailNotice } = useAuth();
  const [state, setState] = useState({ sending: false, message: null });
  const [hidden, setHidden] = useState(false);

  if (!user || user.email_verified || (hidden && !emailNotice)) return null;

  async function resend() {
    setState({ sending: true, message: null });
    try {
      const data = await authApi.resendVerification();
      setState({ sending: false, message: data.detail });
    } catch (e) {
      setState({ sending: false, message: errorMessage(e) });
    }
  }

  return (
    <div className="border-b border-accent/40 bg-accent-soft">
      <Container className="flex flex-wrap items-center gap-3 py-2.5 text-sm">
        <MailCheck className="size-4 shrink-0" aria-hidden />
        <p className="flex-1">
          {emailNotice ? <strong>Confirm your email to continue. </strong> : null}
          Check your inbox for the link we sent to <strong>{user.email}</strong>.
          {state.message && <span className="ml-1 text-muted">{state.message}</span>}
        </p>
        <Button size="sm" variant="secondary" onClick={resend} loading={state.sending}>
          Resend link
        </Button>
        <button
          type="button"
          className="rounded p-1 text-muted hover:text-text"
          aria-label="Hide"
          onClick={() => {
            setHidden(true);
            dismissEmailNotice();
          }}
        >
          <X className="size-4" />
        </button>
      </Container>
    </div>
  );
}
