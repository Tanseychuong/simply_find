import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { FileText } from "lucide-react";
import { authApi } from "../../api/auth";
import { errorMessage, fieldErrors } from "../../api/client";
import AuthCard, { PasswordInput } from "../../components/auth/AuthCard";
import { Alert, Button, ButtonLink, Field, Spinner } from "../../components/ui";
import { useApi, useTitle } from "../../lib/hooks";
import { PASSWORD_HINT } from "./Register";
import { useFinishSignIn } from "./useFinishSignIn";

/*
  /claim?token=... from the email sent after a hiring team signed a student
  up at their desk during a recruitment drive. Setting a password claims the
  account (and signs in); unclaimed accounts are deleted after 14 days.
*/
export default function Claim() {
  useTitle("Claim your account");
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const finish = useFinishSignIn("/profile");
  const { data, loading, error } = useApi((signal) => (token ? authApi.claimInfo(token, { signal }) : Promise.reject(new Error("no token"))), [token]);
  const [password, setPassword] = useState("");
  const [state, setState] = useState({ busy: false, error: null, fields: {} });

  async function submit(e) {
    e.preventDefault();
    setState({ busy: true, error: null, fields: {} });
    try {
      finish(await authApi.claim(token, password));
    } catch (err) {
      const fields = fieldErrors(err);
      setState({ busy: false, fields, error: fields.password ? null : fields.token || errorMessage(err) });
    }
  }

  if (loading) return <Spinner />;
  if (error || !data) {
    const msg = error?.response ? fieldErrors(error).token || errorMessage(error) : "This link is incomplete.";
    return (
      <AuthCard title="This link doesn't work" subtitle={msg}>
        <p className="mb-4 text-sm text-muted">If you already set a password, sign in. Otherwise ask the hiring team to send the email again.</p>
        <ButtonLink to="/login" className="w-full">Sign in</ButtonLink>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      wide
      title={`Welcome, ${data.name.split(" ")[0]}`}
      subtitle={`${data.company} signed you up at ${data.drive}. Choose a password to keep your SimplyFind account.`}
    >
      {data.documents?.length > 0 && (
        <div className="mb-6 rounded-lg border border-border p-4">
          <p className="mb-2 text-sm font-medium">Documents scanned for you on the day</p>
          <ul className="space-y-1.5">
            {data.documents.map((d) => (
              <li key={d.id} className="flex items-center gap-2 text-sm text-muted">
                <FileText className="size-4 shrink-0" aria-hidden /> {d.title}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-xs text-muted">They're in your document vault. You can rename or delete them any time.</p>
        </div>
      )}
      <form onSubmit={submit} className="space-y-4" noValidate>
        {state.error && <Alert tone="danger">{state.error}</Alert>}
        <Field label="Email">
          <p className="text-sm">{data.email}</p>
        </Field>
        <Field label="Choose a password" htmlFor="password" error={state.fields.password} hint={PASSWORD_HINT}>
          <PasswordInput id="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} invalid={Boolean(state.fields.password)} autoFocus />
        </Field>
        <p className="text-xs text-muted">Accounts that aren't claimed within 14 days are deleted, with their documents.</p>
        <Button type="submit" className="w-full" loading={state.busy} disabled={!password}>Claim my account</Button>
      </form>
    </AuthCard>
  );
}
