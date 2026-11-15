import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { authApi } from "../../api/auth";
import { errorMessage, fieldErrors } from "../../api/client";
import AuthCard, { Divider, PasswordInput } from "../../components/auth/AuthCard";
import GoogleButton, { googleEnabled } from "../../components/auth/GoogleButton";
import { Alert, Button, Field, Input } from "../../components/ui";
import { useTitle } from "../../lib/hooks";
import { useFinishSignIn } from "./useFinishSignIn";

// Matches the backend's AUTH_PASSWORD_VALIDATORS (minimum length 10).
export const PASSWORD_HINT = "At least 10 characters. Avoid common passwords and ones like your name or email.";

export default function Register() {
  useTitle("Create your account");
  const [params] = useSearchParams();
  // ?drive=CODE: signed up from a recruitment drive's QR code.
  const drive = (params.get("drive") || "").replace(/[^A-Za-z0-9]/g, "").slice(0, 20);
  const finish = useFinishSignIn("/profile");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState(null);
  const [busy, setBusy] = useState(false);

  async function run(request) {
    setBusy(true);
    setErrors({});
    setMessage(null);
    try {
      finish(await request());
    } catch (err) {
      const fields = fieldErrors(err);
      setErrors(fields);
      setMessage(Object.keys(fields).length ? null : errorMessage(err));
      setBusy(false);
    }
  }

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  const next = params.get("next");

  return (
    <AuthCard
      title="Create your account"
      subtitle="Free for students and recent graduates. Build your profile once and apply with your documents."
      footer={<>Already have an account? <Link to={`/login${next ? `?next=${encodeURIComponent(next)}` : ""}`} className="font-medium text-brand hover:underline">Sign in</Link></>}
    >
      {drive && <Alert tone="info" className="mb-4">You're signing up through a recruitment drive. The hiring team will see that you registered.</Alert>}
      <form
        className="space-y-4"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          run(() => authApi.register({ name: form.name.trim(), email: form.email.trim(), password: form.password, ...(drive ? { drive } : {}) }));
        }}
      >
        {message && <Alert tone="danger">{message}</Alert>}
        <Field label="Full name" htmlFor="name" error={errors.name}>
          <Input id="name" autoComplete="name" value={form.name} onChange={set("name")} invalid={Boolean(errors.name)} autoFocus />
        </Field>
        <Field label="Email" htmlFor="email" error={errors.email} hint="We'll send a link to confirm it. You need a confirmed email to apply.">
          <Input id="email" type="email" autoComplete="email" value={form.email} onChange={set("email")} invalid={Boolean(errors.email)} />
        </Field>
        <Field label="Password" htmlFor="password" error={errors.password} hint={PASSWORD_HINT}>
          <PasswordInput id="password" autoComplete="new-password" value={form.password} onChange={set("password")} invalid={Boolean(errors.password)} />
        </Field>
        <p className="text-xs text-muted">
          By creating an account you agree to how we handle your data, described in our <Link to="/privacy" className="text-brand hover:underline">privacy notice</Link>.
        </p>
        <Button type="submit" className="w-full" loading={busy} disabled={!form.name.trim() || !form.email.trim() || !form.password}>
          Create account
        </Button>
      </form>
      {googleEnabled && !drive && (
        <>
          <Divider>or</Divider>
          <GoogleButton text="signup_with" onCredential={(credential) => run(() => authApi.google(credential))} />
        </>
      )}
    </AuthCard>
  );
}
