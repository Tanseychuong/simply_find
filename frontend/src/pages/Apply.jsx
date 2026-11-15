import { useId, useMemo, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { ArrowLeft, CheckCircle2, FileText, ShieldCheck, UserRoundPen } from "lucide-react";
import { opportunitiesApi } from "../api/opportunities";
import { ACCEPTED_FILES, DOCUMENT_KINDS, applicationsApi, profileApi } from "../api/profile";
import { errorMessage, fieldErrors } from "../api/client";
import { checkFile, formatSize } from "../components/profile/DocumentUpload";
import { Alert, Button, ButtonLink, Card, Container, Field, Input, Select, Spinner, Textarea } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { organisationOf } from "../lib/format";
import { useApi, useTitle } from "../lib/hooks";
import NotFound from "./NotFound";

const NEW_FILE = "__new__";

/** Best vault match for a file question, by kind words in its label ("Transcript", "CV"...). */
function guessDocument(label, docs) {
  const l = label.toLowerCase();
  const kind =
    /transcript|result|grade/.test(l) ? "transcript"
      : /\bcv\b|resume|résumé|curriculum/.test(l) ? "cv"
        : /certificate|diploma|degree/.test(l) ? "certificate"
          : /recommend|reference/.test(l) ? "recommendation"
            : /\bid\b|passport|identity|national/.test(l) ? "id_document" : null;
  return kind ? docs.find((d) => d.kind === kind) : null;
}

function FileQuestion({ req, docs, value, onChange, invalid }) {
  const id = useId();
  const usingNew = value instanceof File || value === NEW_FILE;
  const [fileError, setFileError] = useState(null);
  return (
    <div className="space-y-2">
      <Select
        id={`q-${req.id}`}
        value={usingNew ? NEW_FILE : value || ""}
        onChange={(e) => onChange(e.target.value)}
        invalid={invalid}
      >
        <option value="">{req.required ? "Choose a document" : "No document"}</option>
        {docs.length > 0 && (
          <optgroup label="From my vault">
            {docs.map((d) => (
              <option key={d.id} value={`vault:${d.id}`}>
                {d.title} ({DOCUMENT_KINDS[d.kind] || d.kind})
              </option>
            ))}
          </optgroup>
        )}
        <option value={NEW_FILE}>Upload a new file...</option>
      </Select>
      {usingNew && (
        <div className="rounded-lg border border-dashed border-border p-3">
          <label htmlFor={id} className="sr-only">File for {req.label}</label>
          <input
            id={id}
            type="file"
            accept={ACCEPTED_FILES}
            className="block w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-brand-soft file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-brand-strong"
            onChange={(e) => {
              const f = e.target.files?.[0];
              const problem = f ? checkFile(f) : null;
              setFileError(problem);
              onChange(f && !problem ? f : NEW_FILE);
            }}
          />
          {value instanceof File && <p className="mt-1 text-xs text-muted">{value.name}, {formatSize(value.size)}</p>}
          {fileError && <p className="mt-1 text-xs text-danger">{fileError}</p>}
          <p className="mt-1 text-xs text-muted">
            PDF, JPG or PNG. Tip: add it to your <Link to="/profile/documents" className="text-brand hover:underline">vault</Link> to reuse it next time.
          </p>
        </div>
      )}
    </div>
  );
}

function Question({ req, docs, value, onChange, error }) {
  const common = { id: `q-${req.id}`, invalid: Boolean(error) };
  let input;
  switch (req.kind) {
    case "long_text":
      input = (
        <>
          <Textarea {...common} rows={6} maxLength={10000} value={value || ""} onChange={(e) => onChange(e.target.value)} />
          <p className="text-right text-xs text-muted">{(value || "").length}/10,000</p>
        </>
      );
      break;
    case "url":
      input = <Input {...common} type="url" placeholder="https://" value={value || ""} onChange={(e) => onChange(e.target.value)} />;
      break;
    case "yes_no":
    case "choice": {
      const options = req.kind === "yes_no" ? [["yes", "Yes"], ["no", "No"]] : req.options.map((o) => [o, o]);
      input = (
        <div role="radiogroup" aria-labelledby={`q-${req.id}-label`} className="flex flex-wrap gap-2">
          {options.map(([v, l]) => (
            <label key={v} className="flex cursor-pointer items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm has-[:checked]:border-brand has-[:checked]:bg-brand-soft">
              <input type="radio" name={`q-${req.id}`} value={v} checked={value === v} onChange={() => onChange(v)} className="accent-brand" />
              {l}
            </label>
          ))}
        </div>
      );
      break;
    }
    case "file":
      input = <FileQuestion req={req} docs={docs} value={value} onChange={onChange} invalid={Boolean(error)} />;
      break;
    default:
      input = <Input {...common} maxLength={500} value={value || ""} onChange={(e) => onChange(e.target.value)} />;
  }
  return (
    <div className="space-y-1.5">
      <label id={`q-${req.id}-label`} htmlFor={`q-${req.id}`} className="block text-sm font-medium">
        {req.label} {req.required ? <span className="text-danger" aria-label="required">*</span> : <span className="font-normal text-muted">(optional)</span>}
      </label>
      {req.help_text && <p className="text-xs text-muted">{req.help_text}</p>}
      {input}
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}

function ApplyForm({ opp, docs }) {
  const [answers, setAnswers] = useState(() => {
    // Pre-pick the obvious vault document for each file question.
    const initial = {};
    for (const r of opp.requirements) {
      if (r.kind === "file") {
        const doc = guessDocument(r.label, docs);
        if (doc) initial[r.id] = `vault:${doc.id}`;
      }
    }
    return initial;
  });
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState({ busy: false, progress: 0, error: null, fields: {}, done: false });
  const org = organisationOf(opp);

  function validate() {
    const fields = {};
    for (const r of opp.requirements) {
      const v = answers[r.id];
      const empty = v === undefined || v === "" || v === NEW_FILE || (typeof v === "string" && !v.trim());
      if (r.required && empty) fields[`answer_${r.id}`] = r.kind === "file" ? "Choose a document or upload one." : "This is required.";
      if (r.kind === "url" && !empty && !/^https?:\/\//i.test(v)) fields[`answer_${r.id}`] = "Enter a full link starting with https://";
    }
    return fields;
  }

  async function submit(e) {
    e.preventDefault();
    const fields = validate();
    if (Object.keys(fields).length) {
      setState({ ...state, fields, error: "Some answers need attention." });
      document.getElementById(`q-${Object.keys(fields)[0].replace("answer_", "")}`)?.focus();
      return;
    }
    setState({ busy: true, progress: 0, error: null, fields: {}, done: false });
    const payload = Object.fromEntries(
      Object.entries(answers).filter(([, v]) => v !== NEW_FILE).map(([k, v]) => [k, typeof v === "string" ? v.trim() : v]),
    );
    try {
      await applicationsApi.submit(opp.id, payload, (ev) =>
        setState((s) => ({ ...s, progress: ev.total ? Math.round((100 * ev.loaded) / ev.total) : 0 })),
      );
      setState({ busy: false, progress: 100, error: null, fields: {}, done: true });
      window.scrollTo(0, 0);
    } catch (err) {
      const f = fieldErrors(err);
      const eligibility = err?.response?.data?.eligibility;
      setState({
        busy: false,
        progress: 0,
        fields: f,
        done: false,
        error: Array.isArray(eligibility) ? eligibility.join(" ") : f.consent || (Object.keys(f).length ? "Some answers need attention." : errorMessage(err)),
      });
    }
  }

  if (state.done) {
    return (
      <Card className="p-5 sm:p-8 text-center">
        <CheckCircle2 className="mx-auto size-12 text-success" aria-hidden />
        <h2 className="mt-4 text-2xl font-semibold">Application sent</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted">
          {org} has your application. We'll email you when its status changes, and you can see who opens your documents on your profile.
        </p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <ButtonLink to="/applications">Track my applications</ButtonLink>
          <ButtonLink to="/opportunities" variant="secondary">Find more roles</ButtonLink>
        </div>
      </Card>
    );
  }

  return (
    <form onSubmit={submit} noValidate>
      <Card className="space-y-6 p-4 sm:p-6">
        {state.error && <Alert tone="danger">{state.error}</Alert>}
        {opp.requirements.length === 0 && <p className="text-sm text-muted">This role only needs your profile. Confirm below to apply.</p>}
        {opp.requirements.map((r) => (
          <Question
            key={r.id}
            req={r}
            docs={docs}
            value={answers[r.id]}
            onChange={(v) => {
              setAnswers((a) => ({ ...a, [r.id]: v }));
              // The old message no longer applies once the answer changes.
              setState((s) => (s.fields[`answer_${r.id}`] ? { ...s, fields: { ...s.fields, [`answer_${r.id}`]: undefined } } : s));
            }}
            error={state.fields[`answer_${r.id}`]}
          />
        ))}
        <div className="rounded-lg bg-surface-2 p-4">
          <label className="flex cursor-pointer items-start gap-3 text-sm">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 size-4 accent-brand" />
            <span>
              I agree to share this application with <strong>{org}</strong>: my answers, the documents I attached, and my profile (studies
              and skills). They see my email and phone only if they shortlist me. My date of birth is never shared.
            </span>
          </label>
        </div>
        {state.busy && state.progress > 0 && state.progress < 100 && (
          <div className="h-1.5 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={state.progress} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full bg-brand transition-all" style={{ width: `${state.progress}%` }} />
          </div>
        )}
        <Button type="submit" size="lg" className="w-full sm:w-auto" loading={state.busy} disabled={!consent}>Send application</Button>
      </Card>
    </form>
  );
}

export default function Apply() {
  const { id } = useParams();
  const { user } = useAuth();
  const { data, loading, error } = useApi(
    (signal) =>
      Promise.all([
        opportunitiesApi.get(id, { signal }),
        profileApi.eligibility(id, { signal }),
        profileApi.documents({ signal }),
      ]).then(([opp, eligibility, docs]) => ({ opp, eligibility, docs })),
    [id],
  );
  const opp = data?.opp;
  useTitle(opp ? `Apply: ${opp.title}` : "Apply");
  const backTo = useMemo(() => `/opportunities/${id}`, [id]);

  if (loading && !data) return <Spinner />;
  if (error?.response?.status === 404) return <NotFound />;
  if (error) {
    return (
      <Container className="py-8 sm:py-10">
        <Alert tone="danger">{errorMessage(error)}</Alert>
      </Container>
    );
  }
  if (opp.application_method !== "in_app") return <Navigate to={backTo} replace />;

  const { eligibility, docs } = data;
  let blocker = null;
  if (opp.has_applied) {
    blocker = (
      <Alert tone="success">
        You've already applied for this role. <Link to="/applications" className="font-medium underline">Track it here</Link>.
      </Alert>
    );
  } else if (!opp.is_open) {
    blocker = <Alert tone="warning">Applications for this role have closed.</Alert>;
  } else if (!user.email_verified) {
    blocker = (
      <Card className="p-4 sm:p-6">
        <h2 className="font-semibold">Confirm your email first</h2>
        <p className="mt-1 text-sm text-muted">We sent a link to {user.email} when you signed up. Use the bar at the top of the page to send it again.</p>
      </Card>
    );
  } else if (!eligibility.eligible) {
    blocker = (
      <Card className="p-4 sm:p-6">
        <div className="flex items-start gap-3">
          <UserRoundPen className="mt-0.5 size-5 shrink-0 text-accent" aria-hidden />
          <div>
            <h2 className="font-semibold">You can't apply for this role yet</h2>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
              {eligibility.reasons.map((r) => <li key={r}>{r}</li>)}
            </ul>
            <ButtonLink to="/profile" className="mt-4">Update my profile</ButtonLink>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Container className="py-6 sm:py-8">
      <div className="mx-auto max-w-2xl">
        <Link to={backTo} className="mb-6 inline-flex items-center gap-1 text-sm text-muted hover:text-text">
          <ArrowLeft className="size-4" /> Back to the role
        </Link>
        <p className="text-sm font-medium text-muted">{organisationOf(opp)}</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">Apply: {opp.title}</h1>
        <div className="mt-3 mb-6 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
          <span className="inline-flex items-center gap-1"><ShieldCheck className="size-4" /> Your profile is attached automatically</span>
          <span className="inline-flex items-center gap-1"><FileText className="size-4" /> {docs.length} document{docs.length === 1 ? "" : "s"} in your vault</span>
        </div>
        {blocker || <ApplyForm opp={opp} docs={docs} />}
      </div>
    </Container>
  );
}
