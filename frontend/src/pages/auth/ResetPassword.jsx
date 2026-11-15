import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import { authApi } from "../../api/auth";
import { errorMessage, fieldErrors } from "../../api/client";
import AuthCard, { PasswordInput } from "../../components/auth/AuthCard";
import { Alert, Button, ButtonLink, Field } from "../../components/ui";
import { useTitle } from "../../lib/hooks";
import { PASSWORD_HINT } from "./Register";

/* Opened from the reset email: /reset-password?uid=...&token=... */
export default function ResetPassword() {
  useTitle("Choose a new password");
  const [params] = useSearchParams();
  const uid = params.get("uid") || "";
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [state, setState] = useState({ busy: false, error: null, fields: {}, done: null });

  async function submit(e) {
    e.preventDefault();
    if (password !== confirm) {
      setState({ ...state, fields: { confirm: "The two passwords don't match." } });
      return;
    }
    setState({ busy: true, error: null, fields: {}, done: null });
    try {
      const data = await authApi.passwordResetConfirm({ uid, token, password });
      setState({ busy: false, fields: {}, done: data.detail });
    } catch (err) {
      const fields = fieldErrors(err);
      const linkProblem = fields.uid || fields.token || fields.non_field_errors;
      setState({ busy: false, fields, error: linkProblem || (fields.password ? null : errorMessage(err)) });
    }
  }

  if (!uid || !token) {
    return (
      <AuthCard title="This link is incomplete" subtitle="Open the link from your email again, or ask for a new one.">
        <ButtonLink to="/forgot-password" className="w-full">Ask for a new link</ButtonLink>
      </AuthCard>
    );
  }

  if (state.done) {
    return (
      <AuthCard title="Password changed">
        <div className="space-y-4 text-center">
          <CheckCircle2 className="mx-auto size-10 text-success" aria-hidden />
          <p className="text-sm">{state.done}</p>
          <p className="text-xs text-muted">You've been signed out everywhere else, for your safety.</p>
          <ButtonLink to="/login" className="w-full">Sign in</ButtonLink>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Choose a new password">
      <form onSubmit={submit} className="space-y-4" noValidate>
        {state.error && (
          <Alert tone="danger">
            {state.error} <Link to="/forgot-password" className="font-medium underline">Ask for a new link</Link>
          </Alert>
        )}
        <Field label="New password" htmlFor="password" error={state.fields.password} hint={PASSWORD_HINT}>
          <PasswordInput id="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} invalid={Boolean(state.fields.password)} autoFocus />
        </Field>
        <Field label="Type it again" htmlFor="confirm" error={state.fields.confirm}>
          <PasswordInput id="confirm" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} invalid={Boolean(state.fields.confirm)} />
        </Field>
        <Button type="submit" className="w-full" loading={state.busy} disabled={!password || !confirm}>Save new password</Button>
      </form>
    </AuthCard>
  );
}
