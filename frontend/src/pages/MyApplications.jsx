import { useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, FileText, Inbox } from "lucide-react";
import { APPLICATION_STATUS, applicationsApi } from "../api/profile";
import { errorMessage } from "../api/client";
import { Alert, Badge, Button, ButtonLink, Card, Container, EmptyState, Spinner, cx } from "../components/ui";
import { formatDate } from "../lib/format";
import { useApi, useTitle } from "../lib/hooks";

// What each status means for the student, in plain words.
const NEXT = {
  submitted: "The hiring team has your application.",
  reviewing: "The hiring team is reading your application.",
  shortlisted: "You're on the shortlist. The team can now see your email and phone, and may contact you.",
  hired: "Congratulations! The team will be in touch about next steps.",
  rejected: "The team chose other applicants this time.",
  withdrawn: "You withdrew this application. Its answers and files were deleted.",
};
// Can no longer be withdrawn.
const FINAL = new Set(["hired", "rejected", "withdrawn"]);
// Shown under "Closed". A hire stays under "Active": it's the news the student is looking for.
const CLOSED = new Set(["rejected", "withdrawn"]);

function Answer({ a }) {
  if (a.kind === "file") {
    return a.has_file ? (
      <a href={applicationsApi.answerFileUrl(a.id)} className="inline-flex items-center gap-1 text-brand hover:underline">
        <FileText className="size-4" /> {a.original_filename || "Download"}
      </a>
    ) : (
      <span className="text-muted">No file</span>
    );
  }
  return <span className="whitespace-pre-line">{a.value || <span className="text-muted">No answer</span>}</span>;
}

function ApplicationCard({ app, onChange }) {
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [state, setState] = useState({ busy: false, error: null });
  const status = APPLICATION_STATUS[app.status] || { label: app.status, tone: "neutral" };
  const org = app.job.company?.name || app.job.organization;

  async function withdraw() {
    setState({ busy: true, error: null });
    try {
      onChange(await applicationsApi.withdraw(app.id));
      setConfirm(false);
      setState({ busy: false, error: null });
    } catch (err) {
      setState({ busy: false, error: errorMessage(err) });
    }
  }

  return (
    <Card className="p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted">{org}</p>
          <h2 className="font-semibold">
            <Link to={`/opportunities/${app.job.id}`} className="hover:text-brand">{app.job.title}</Link>
          </h2>
          <p className="mt-1 text-xs text-muted">Applied {formatDate(app.submitted_at)}</p>
        </div>
        <Badge tone={status.tone} className="self-start">{status.label}</Badge>
      </div>
      <p className="mt-3 text-sm text-muted">{NEXT[app.status]}</p>
      {state.error && <Alert tone="danger" className="mt-3">{state.error}</Alert>}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {app.answers?.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            <ChevronDown className={cx("size-4 transition-transform", open && "rotate-180")} /> {open ? "Hide" : "Show"} my answers
          </Button>
        )}
        {!FINAL.has(app.status) &&
          (confirm ? (
            <span className="inline-flex flex-wrap items-center gap-2 text-sm">
              Withdraw? Your answers and files will be deleted.
              <Button variant="danger" size="sm" loading={state.busy} onClick={withdraw}>Withdraw</Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirm(false)}>Keep it</Button>
            </span>
          ) : (
            <Button variant="ghost" size="sm" className="text-danger" onClick={() => setConfirm(true)}>Withdraw</Button>
          ))}
      </div>
      {open && (
        <dl className="mt-4 space-y-3 border-t border-border pt-4">
          {app.answers.map((a) => (
            <div key={a.id}>
              <dt className="text-xs font-medium text-muted">{a.label}</dt>
              <dd className="mt-0.5 text-sm"><Answer a={a} /></dd>
            </div>
          ))}
        </dl>
      )}
    </Card>
  );
}

export default function MyApplications() {
  useTitle("My applications");
  const { data, loading, error, setData } = useApi((signal) => applicationsApi.mine({ signal }), []);
  const [filter, setFilter] = useState("active");
  const apps = data || [];
  const shown = apps.filter((a) => (filter === "active" ? !CLOSED.has(a.status) : CLOSED.has(a.status)));
  const activeCount = apps.filter((a) => !CLOSED.has(a.status)).length;

  return (
    <Container className="py-8">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-3xl font-bold tracking-tight">My applications</h1>
        <p className="mt-1 text-sm text-muted">Applications you made on SimplyFind. Roles on other websites are tracked there.</p>
        {apps.length > 0 && (
          <div className="mt-6 inline-flex rounded-lg border border-border bg-surface p-1" role="tablist">
            {[
              ["active", `Active (${activeCount})`],
              ["closed", `Closed (${apps.length - activeCount})`],
            ].map(([key, label]) => (
              <button
                key={key}
                role="tab"
                aria-selected={filter === key}
                onClick={() => setFilter(key)}
                className={cx("rounded-md px-3 py-1.5 text-sm font-medium", filter === key ? "bg-brand-soft text-brand-strong" : "text-muted hover:text-text")}
              >
                {label}
              </button>
            ))}
          </div>
        )}
        <div className="mt-6 space-y-4">
          {loading && !data ? (
            <Spinner />
          ) : error ? (
            <Alert tone="danger">{errorMessage(error)}</Alert>
          ) : apps.length === 0 ? (
            <EmptyState icon={Inbox} title="No applications yet" action={<ButtonLink to="/opportunities?apply_on_site=true">Find roles you can apply for here</ButtonLink>}>
              Roles marked "Apply on SimplyFind" take your profile and vault documents in one go.
            </EmptyState>
          ) : shown.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted">Nothing here.</p>
          ) : (
            shown.map((a) => <ApplicationCard key={a.id} app={a} onChange={(na) => setData(apps.map((x) => (x.id === na.id ? na : x)))} />)
          )}
        </div>
      </div>
    </Container>
  );
}
