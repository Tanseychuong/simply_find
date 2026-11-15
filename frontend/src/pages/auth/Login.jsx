import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { authApi } from "../../api/auth";
import { errorCodeOf, errorMessage, fieldErrors } from "../../api/client";
import AuthCard, { Divider, PasswordInput } from "../../components/auth/AuthCard";
import GoogleButton, { googleEnabled } from "../../components/auth/GoogleButton";
import { Alert, Button, Field, Input } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { useTitle } from "../../lib/hooks";
import { useFinishSignIn } from "./useFinishSignIn";

function CodeStep({ mfaToken, onExpired }) {
  const finish = useFinishSignIn();
  const [code, setCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const [state, setState] = useState({ busy: false, error: null });

  async function submit(e) {
    e.preventDefault();
    setState({ busy: true, error: null });
    try {
      finish(await authApi.mfaLogin(mfaToken, code.trim()));
    } catch (err) {
      if (errorCodeOf(err) === "mfa_expired") return onExpired(errorMessage(err));
      setState({ busy: false, error: errorMessage(err) });
    }
  }

  return (
    <form onSubmit={submit} className="space-y-4" noValidate>
      <div className="flex items-start gap-3 rounded-lg bg-brand-soft p-3 text-sm">
        <ShieldCheck className="mt-0.5 size-5 shrink-0 text-brand" aria-hidden />
        <p>
          {useRecovery
            ? "Enter one of the recovery codes you saved when you turned on two-step sign-in. Each code works once."
            : "Open your authenticator app and enter the 6-digit code for SimplyFind."}
        </p>
      </div>
      {state.error && <Alert tone="danger">{state.error}</Alert>}
      <Field label={useRecovery ? "Recovery code" : "Code"} htmlFor="code">
        <Input
          id="code"
          value={code}
          onChange={(e) => setCode(useRecovery ? e.target.value : e.target.value.replace(/\D/g, "").slice(0, 6))}
          inputMode={useRecovery ? "text" : "numeric"}
          autoComplete="one-time-code"
          autoFocus
          placeholder={useRecovery ? "xxxx-xxxx" : "123456"}
          className="text-center text-lg tracking-widest"
        />
      </Field>
      <Button type="submit" className="w-full" loading={state.busy} disabled={!code.trim()}>Verify and sign in</Button>
      <button
        type="button"
        className="w-full text-center text-sm font-medium text-brand hover:underline"
        onClick={() => {
          setUseRecovery((v) => !v);
          setCode("");
        }}
      >
        {useRecovery ? "Use a code from my app instead" : "Lost your phone? Use a recovery code"}
      </button>
    </form>
  );
}

export default function Login() {
  useTitle("Sign in");
  const [params] = useSearchParams();
  const { user } = useAuth();
  const finish = useFinishSignIn();
  // ?mfa=1: the API asked a signed-in team member to sign in again with a code.
  const reauth = params.has("mfa") && user;
  const [form, setForm] = useState({ email: reauth ? user.email : "", password: "" });
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);
  const [mfaToken, setMfaToken] = useState(null);

  async function run(request) {
    setBusy(true);
    setErrors({});
    setMessage(null);
    try {
      const step = finish(await request());
      if (step?.mfaToken) setMfaToken(step.mfaToken);
    } catch (err) {
      setErrors(fieldErrors(err));
      setMessage(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const next = params.get("next");
  const registerLink = `/register${next ? `?next=${encodeURIComponent(next)}` : ""}`;

  if (mfaToken) {
    return (
      <AuthCard title="Two-step sign-in" subtitle={`Signing in as ${form.email}`}>
        <CodeStep
          mfaToken={mfaToken}
          onExpired={(msg) => {
            setMfaToken(null);
            setMessage(msg);
          }}
        />
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title={reauth ? "Confirm it's you" : "Sign in"}
      subtitle={reauth ? "Company and staff tools need a fresh two-step sign-in. Enter your password, then a code." : "Welcome back to SimplyFind."}
      footer={!reauth && <>New to SimplyFind? <Link to={registerLink} className="font-medium text-brand hover:underline">Create an account</Link></>}
    >
      <form
        className="space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          run(() => authApi.login(form.email.trim(), form.password));
        }}
      >
        {message && <Alert tone="danger">{message}</Alert>}
        <Field label="Email" htmlFor="email" error={errors.email}>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            value={form.email}
            readOnly={Boolean(reauth)}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            invalid={Boolean(errors.email)}
            autoFocus={!reauth}
          />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password}>
          <PasswordInput
            id="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            invalid={Boolean(errors.password)}
            autoFocus={Boolean(reauth)}
          />
        </Field>
        <div className="flex justify-end">
          <Link to="/forgot-password" className="text-sm font-medium text-brand hover:underline">Forgot your password?</Link>
        </div>
        <Button type="submit" className="w-full" loading={busy} disabled={!form.email || !form.password}>Sign in</Button>
      </form>
      {googleEnabled && !reauth && (
        <>
          <Divider>or</Divider>
          <GoogleButton onCredential={(credential) => run(() => authApi.google(credential))} />
        </>
      )}
    </AuthCard>
  );
}
