import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Mail, UserPlus } from "lucide-react";
import { TEAM_ROLES, companyApi } from "../../api/company";
import { errorMessage, fieldErrors } from "../../api/client";
import { Alert, Badge, Button, Card, Field, Input, Select, Spinner } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { formatDate } from "../../lib/format";
import { useApi, useTitle } from "../../lib/hooks";

function InviteForm({ perms, onInvited }) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("recruiter");
  const [state, setState] = useState({ busy: false, error: null, sent: null });
  const roles = Object.entries(TEAM_ROLES).filter(([r]) => r !== "owner" || perms.invite_owners);

  async function submit(e) {
    e.preventDefault();
    setState({ busy: true, error: null, sent: null });
    try {
      const inv = await companyApi.invite(email.trim(), role);
      onInvited(inv);
      setEmail("");
      setState({ busy: false, error: null, sent: `Invitation sent to ${inv.email}.` });
    } catch (err) {
      const f = fieldErrors(err);
      setState({ busy: false, error: f.email || f.role || errorMessage(err), sent: null });
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-[1fr_180px_auto] sm:items-end">
        <Field label="Email" htmlFor="invite-email">
          <Input id="invite-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="colleague@company.com" />
        </Field>
        <Field label="Role" htmlFor="invite-role">
          <Select id="invite-role" value={role} onChange={(e) => setRole(e.target.value)}>
            {roles.map(([v, r]) => <option key={v} value={v}>{r.label}</option>)}
          </Select>
        </Field>
        <Button type="submit" loading={state.busy} disabled={!email.trim()}>
          <UserPlus className="size-4" /> Invite
        </Button>
      </div>
      <p className="text-xs text-muted">{TEAM_ROLES[role].help}. The link works for 7 days and only for that email address.</p>
      {state.error && <Alert tone="danger">{state.error}</Alert>}
      {state.sent && <Alert tone="success">{state.sent}</Alert>}
    </form>
  );
}

export default function Team() {
  useTitle("Team");
  const { reload: reloadUser } = useAuth();
  const navigate = useNavigate();
  const { data, loading, error, setData, reload } = useApi((signal) => companyApi.team({ signal }), []);
  const [busy, setBusy] = useState(null);
  const [message, setMessage] = useState(null);

  if (loading && !data) return <Spinner />;
  if (error) return <Alert tone="danger">{errorMessage(error)}</Alert>;
  const perms = data.my_permissions;

  async function act(key, fn) {
    setBusy(key);
    setMessage(null);
    try {
      await fn();
    } catch (err) {
      setMessage(errorMessage(err));
    } finally {
      setBusy(null);
    }
  }

  const canRemove = (m) => m.is_you || (m.role === "recruiter" ? perms.remove_recruiters : perms.remove_admins);

  return (
    <div className="space-y-6">
      {message && <Alert tone="danger">{message}</Alert>}
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Team members</h2>
        <ul className="mt-4 divide-y divide-border">
          {data.members.map((m) => (
            <li key={m.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{m.name} {m.is_you && <span className="text-sm font-normal text-muted">(you)</span>}</p>
                <p className="truncate text-sm text-muted">{m.email} · joined {formatDate(m.created_at)}</p>
              </div>
              <div className="flex items-center gap-2">
                {perms.change_roles && !m.is_you ? (
                  <Select
                    aria-label={`Role for ${m.name}`}
                    value={m.role}
                    className="h-9 w-36"
                    disabled={busy === m.id}
                    onChange={(e) => act(m.id, async () => {
                      const updated = await companyApi.changeRole(m.id, e.target.value);
                      setData((d) => ({ ...d, members: d.members.map((x) => (x.id === m.id ? updated : x)) }));
                    })}
                  >
                    {Object.entries(TEAM_ROLES).map(([v, r]) => <option key={v} value={v}>{r.label}</option>)}
                  </Select>
                ) : (
                  <Badge tone={m.role === "owner" ? "brand" : "neutral"}>{TEAM_ROLES[m.role]?.label}</Badge>
                )}
                {canRemove(m) && (
                  <Button
                    variant="ghost"
                    size="sm"
                    loading={busy === `rm-${m.id}`}
                    onClick={() => act(`rm-${m.id}`, async () => {
                      await companyApi.removeMember(m.id);
                      if (m.is_you) {
                        await reloadUser();
                        navigate("/");
                      } else {
                        reload();
                      }
                    })}
                  >
                    {m.is_you ? "Leave" : "Remove"}
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      </Card>

      {perms.invite && (
        <Card className="p-6">
          <h2 className="mb-4 text-lg font-semibold">Invite someone</h2>
          <InviteForm perms={perms} onInvited={(inv) => setData((d) => ({ ...d, invitations: [inv, ...d.invitations] }))} />
          {data.invitations.length > 0 && (
            <>
              <h3 className="mt-6 mb-2 text-sm font-semibold">Waiting to be accepted</h3>
              <ul className="divide-y divide-border">
                {data.invitations.map((inv) => (
                  <li key={inv.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
                    <Mail className="size-4 text-muted" aria-hidden />
                    <span className="min-w-0 flex-1 truncate">{inv.email}</span>
                    <Badge>{TEAM_ROLES[inv.role]?.label}</Badge>
                    <span className="text-xs text-muted">expires {formatDate(inv.expires_at)}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={busy === `inv-${inv.id}`}
                      onClick={() => act(`inv-${inv.id}`, async () => {
                        await companyApi.revokeInvite(inv.id);
                        setData((d) => ({ ...d, invitations: d.invitations.filter((x) => x.id !== inv.id) }));
                      })}
                    >
                      Cancel
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
