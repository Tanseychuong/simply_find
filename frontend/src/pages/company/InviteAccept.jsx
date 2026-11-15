import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Users } from "lucide-react";
import { TEAM_ROLES, companyApi } from "../../api/company";
import { errorMessage } from "../../api/client";
import AuthCard from "../../components/auth/AuthCard";
import { Alert, Button, ButtonLink, Spinner } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { useApi, useTitle } from "../../lib/hooks";

/* /companies/invite/:token, from the invitation email. */
export default function InviteAccept() {
  useTitle("Join your team");
  const { token } = useParams();
  const { user, reload } = useAuth();
  const navigate = useNavigate();
  const { data: inv, loading, error } = useApi((signal) => companyApi.invitation(token, { signal }), [token]);
  const [state, setState] = useState({ busy: false, error: null });

  if (loading) return <Spinner />;
  if (error || !inv) {
    return (
      <AuthCard title="This invitation doesn't work" subtitle={errorMessage(error)}>
        <ButtonLink to="/" className="w-full">Go to SimplyFind</ButtonLink>
      </AuthCard>
    );
  }

  const here = `/companies/invite/${token}`;
  const role = TEAM_ROLES[inv.role]?.label || inv.role;
  const wrongAccount = user && user.email.toLowerCase() !== inv.email.toLowerCase();

  async function accept() {
    setState({ busy: true, error: null });
    try {
      await companyApi.acceptInvitation(token);
      await reload();
      navigate("/company");
    } catch (err) {
      setState({ busy: false, error: errorMessage(err) });
    }
  }

  return (
    <AuthCard
      title={`Join ${inv.company.name}`}
      subtitle={`${inv.invited_by || "Someone on the team"} invited ${inv.email} to join as ${role.toLowerCase()}.`}
    >
      <div className="space-y-4">
        <div className="flex items-center gap-3 rounded-lg bg-surface-2 p-3">
          {inv.company.logo_url ? (
            <img src={inv.company.logo_url} alt="" className="size-10 rounded-lg object-contain" />
          ) : (
            <Users className="size-6 text-brand" aria-hidden />
          )}
          <div className="text-sm">
            <p className="font-medium">{role}</p>
            <p className="text-muted">{TEAM_ROLES[inv.role]?.help}</p>
          </div>
        </div>
        {!inv.is_pending && <Alert tone="warning">This invitation was already used or has expired. Ask for a new one.</Alert>}
        {state.error && <Alert tone="danger">{state.error}</Alert>}
        {inv.is_pending &&
          (!user ? (
            <>
              <ButtonLink to={`/login?next=${encodeURIComponent(here)}`} className="w-full">Sign in as {inv.email}</ButtonLink>
              <ButtonLink to={`/register?next=${encodeURIComponent(here)}`} variant="secondary" className="w-full">Create an account</ButtonLink>
            </>
          ) : wrongAccount ? (
            <Alert tone="warning">
              You're signed in as {user.email}. Sign out and sign in as {inv.email} to accept.
            </Alert>
          ) : (
            <Button onClick={accept} loading={state.busy} className="w-full">Accept and join the team</Button>
          ))}
        <p className="text-xs text-muted">Company tools need two-step sign-in. You'll be asked to set it up after joining.</p>
      </div>
    </AuthCard>
  );
}
