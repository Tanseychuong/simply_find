import { useState } from "react";
import { Link } from "react-router-dom";
import { MailCheck } from "lucide-react";
import { authApi } from "../../api/auth";
import { errorMessage, fieldErrors } from "../../api/client";
import AuthCard from "../../components/auth/AuthCard";
import { Alert, Button, Field, Input } from "../../components/ui";
import { useTitle } from "../../lib/hooks";

export default function ForgotPassword() {
  useTitle("Reset your password");
  const [email, setEmail] = useState("");
  const [state, setState] = useState({ busy: false, error: null, fieldError: null, sent: null });

  async function submit(e) {
    e.preventDefault();
    setState({ busy: true, error: null, fieldError: null, sent: null });
    try {
      const data = await authApi.passwordReset(email.trim());
      setState({ busy: false, sent: data.detail });
    } catch (err) {
      setState({ busy: false, fieldError: fieldErrors(err).email, error: fieldErrors(err).email ? null : errorMessage(err) });
    }
  }

  return (
    <AuthCard
      title="Reset your password"
      subtitle="Enter the email you signed up with and we'll send you a link to choose a new password."
      footer={<Link to="/login" className="font-medium text-brand hover:underline">Back to sign in</Link>}
    >
      {state.sent ? (
        <div className="space-y-3 text-center">
          <MailCheck className="mx-auto size-10 text-brand" aria-hidden />
          {/* The API answers the same whether or not the email has an account. */}
          <p className="text-sm">{state.sent}</p>
          <p className="text-xs text-muted">The link works for an hour. Check your spam folder if it doesn't arrive.</p>
        </div>
      ) : (
        <form onSubmit={submit} className="space-y-4" noValidate>
          {state.error && <Alert tone="danger">{state.error}</Alert>}
          <Field label="Email" htmlFor="email" error={state.fieldError}>
            <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} invalid={Boolean(state.fieldError)} autoFocus />
          </Field>
          <Button type="submit" className="w-full" loading={state.busy} disabled={!email.trim()}>Send reset link</Button>
        </form>
      )}
    </AuthCard>
  );
}
