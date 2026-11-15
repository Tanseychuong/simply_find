import { useId, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AlertTriangle, ArrowDown, ArrowLeft, ArrowUp, Lock, Plus, Trash2 } from "lucide-react";
import { QUESTION_KINDS, companyApi } from "../../api/company";
import { opportunitiesApi } from "../../api/opportunities";
import { errorMessage, fieldErrors } from "../../api/client";
import { Alert, Button, Card, Field, Input, Select, Spinner, Textarea, cx } from "../../components/ui";
import { ROLE_TYPES, WORK_MODES } from "../../lib/format";
import { EMPLOYMENT_TYPES } from "../../lib/filters";
import { useApi, useTitle } from "../../lib/hooks";
import { useCompany } from "./CompanyLayout";

// Optional description sections companies can fill (backend sections.py KINDS).
const SECTION_FIELDS = [
  ["responsibilities", "What the role involves"],
  ["eligibility", "Who can apply"],
  ["benefits", "Benefits"],
  ["documents", "Required documents"],
];

// Words the API flags for review (services.SENSITIVE_TERMS), checked as people type.
const SENSITIVE = /\bage\b|how old|date of birth|\bdob\b|year of birth|\bgender\b|\bsex\b|religio|\bfaith\b|\bchurch\b|\bmosque\b|marital|married|pregnan|tribe|ethnic|disabilit|\bhiv\b/i;

function blocksToText(blocks = []) {
  return blocks.map((b) => (b.type === "li" ? `- ${b.text}` : b.text)).join("\n");
}

function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

const emptyJob = {
  title: "", description: "", category: "", location: "", role_type: "internship", work_mode: "", employment_type: "",
  is_paid: "", duration_months: "", experience_years_max: "0", graduation_year_min: "", graduation_year_max: "",
  accepts_minors: false, application_deadline: "", application_method: "in_app", opportunity_url: "",
  sections: {}, requirements: [
    { label: "CV", kind: "file", help_text: "", required: true, options: [] },
    { label: "Academic transcript", kind: "file", help_text: "", required: true, options: [] },
  ],
};

function fromJob(job) {
  const s = (v) => (v === null || v === undefined ? "" : String(v));
  return {
    title: job.title, description: job.description, category: s(job.category_id), location: job.location,
    role_type: job.role_type, work_mode: job.work_mode, employment_type: job.employment_type || "",
    is_paid: job.is_paid === null ? "" : String(job.is_paid), duration_months: s(job.duration_months),
    experience_years_max: s(job.experience_years_max), graduation_year_min: s(job.graduation_year_min),
    graduation_year_max: s(job.graduation_year_max), accepts_minors: job.accepts_minors,
    application_deadline: toLocalInput(job.application_deadline), application_method: job.application_method,
    opportunity_url: job.opportunity_url || "",
    sections: Object.fromEntries((job.sections || []).filter((x) => SECTION_FIELDS.some(([k]) => k === x.kind)).map((x) => [x.kind, blocksToText(x.blocks)])),
    requirements: job.requirements.map((r) => ({ ...r, options: r.options || [] })),
  };
}

function toPayload(form, { includeRequirements }) {
  const num = (v) => (v === "" ? null : Number(v));
  const body = {
    title: form.title.trim(), description: form.description.trim(), category: num(form.category), location: form.location.trim(),
    role_type: form.role_type, work_mode: form.work_mode, employment_type: form.employment_type,
    is_paid: form.is_paid === "" ? null : form.is_paid === "true",
    duration_months: form.role_type === "internship" ? num(form.duration_months) : null,
    experience_years_max: num(form.experience_years_max) ?? 0,
    graduation_year_min: num(form.graduation_year_min), graduation_year_max: num(form.graduation_year_max),
    accepts_minors: form.accepts_minors,
    application_deadline: form.application_deadline ? new Date(form.application_deadline).toISOString() : null,
    application_method: form.application_method,
    opportunity_url: form.application_method === "external" ? form.opportunity_url.trim() : "",
    sections: SECTION_FIELDS.map(([kind]) => ({ kind, body: (form.sections[kind] || "").trim() })),
  };
  if (includeRequirements) {
    body.requirements = form.application_method === "in_app"
      ? form.requirements.map((r) => ({
          label: r.label.trim(), kind: r.kind, help_text: r.help_text.trim(), required: r.required,
          options: r.kind === "choice" ? r.options.map((o) => o.trim()).filter(Boolean) : [],
        }))
      : [];
  }
  return body;
}

function QuestionEditor({ q, index, count, onChange, onMove, onRemove, error }) {
  const id = useId();
  const set = (k, v) => onChange({ ...q, [k]: v });
  const flagged = SENSITIVE.test(`${q.label} ${q.help_text}`);
  return (
    <div className={cx("rounded-xl border p-4", error ? "border-danger" : "border-border")}>
      <div className="grid gap-3 sm:grid-cols-[1fr_200px]">
        <Field label={`Question ${index + 1}`} htmlFor={`${id}-label`}>
          <Input id={`${id}-label`} value={q.label} maxLength={200} onChange={(e) => set("label", e.target.value)} placeholder="e.g. Why do you want this internship?" />
        </Field>
        <Field label="Answer type" htmlFor={`${id}-kind`}>
          <Select id={`${id}-kind`} value={q.kind} onChange={(e) => set("kind", e.target.value)}>
            {Object.entries(QUESTION_KINDS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </Field>
      </div>
      <div className="mt-3">
        <Field label="Help text (optional)" htmlFor={`${id}-help`}>
          <Input id={`${id}-help`} value={q.help_text} maxLength={500} onChange={(e) => set("help_text", e.target.value)} />
        </Field>
      </div>
      {q.kind === "choice" && (
        <div className="mt-3">
          <Field label="Choices, one per line" htmlFor={`${id}-opts`} hint="At least two.">
            <Textarea id={`${id}-opts`} rows={3} value={q.options.join("\n")} onChange={(e) => set("options", e.target.value.split("\n"))} />
          </Field>
        </div>
      )}
      {flagged && (
        <p className="mt-3 inline-flex items-start gap-1.5 text-xs text-danger">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
          This may ask about age, gender, religion or another protected characteristic. The job will go to manual review, and it may be refused.
        </p>
      )}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-brand" checked={q.required} onChange={(e) => set("required", e.target.checked)} />
          Required
        </label>
        <div className="flex gap-1">
          <Button type="button" variant="ghost" size="sm" disabled={index === 0} onClick={() => onMove(-1)} aria-label="Move up"><ArrowUp className="size-4" /></Button>
          <Button type="button" variant="ghost" size="sm" disabled={index === count - 1} onClick={() => onMove(1)} aria-label="Move down"><ArrowDown className="size-4" /></Button>
          <Button type="button" variant="ghost" size="sm" onClick={onRemove} aria-label={`Remove question ${index + 1}`}><Trash2 className="size-4" /></Button>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children, intro }) {
  return (
    <Card className="p-6">
      <h2 className="text-lg font-semibold">{title}</h2>
      {intro && <p className="mt-1 text-sm text-muted">{intro}</p>}
      <div className="mt-5 space-y-5">{children}</div>
    </Card>
  );
}

function Form({ job, categories }) {
  const id = useId();
  const navigate = useNavigate();
  const { company } = useCompany();
  const [form, setForm] = useState(() => (job ? fromJob(job) : emptyJob));
  const [state, setState] = useState({ busy: false, error: null, fields: {}, notice: null });
  const [closing, setClosing] = useState(false);
  const locked = Boolean(job && job.application_count > 0); // questions can't change once people have applied
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e?.target ? (e.target.type === "checkbox" ? e.target.checked : e.target.value) : e }));
  const setQuestions = (fn) => setForm((f) => ({ ...f, requirements: fn(f.requirements) }));
  const f = state.fields;
  const thisYear = new Date().getFullYear();
  const years = Array.from({ length: 12 }, (_, i) => thisYear - 4 + i);

  async function submit(e) {
    e.preventDefault();
    setState({ busy: true, error: null, fields: {}, notice: null });
    try {
      const body = toPayload(form, { includeRequirements: !locked });
      const saved = job ? await companyApi.updateJob(job.id, body) : await companyApi.createJob(body);
      navigate("/company", { state: { notice: saved.status === "approved" ? `"${saved.title}" is live.` : `"${saved.title}" was sent for review.` } });
    } catch (err) {
      const fields = fieldErrors(err);
      // requirements errors come back as a list, one entry per question
      const reqErrors = err?.response?.data?.requirements;
      if (Array.isArray(reqErrors)) {
        reqErrors.forEach((r, i) => {
          if (r && typeof r === "object") fields[`q${i}`] = Object.values(r).flat().join(" ");
        });
      }
      setState({ busy: false, fields, error: Object.keys(fields).length ? "Check the highlighted fields." : errorMessage(err), notice: null });
      window.scrollTo(0, 0);
    }
  }

  async function closeJob() {
    try {
      await companyApi.closeJob(job.id);
      navigate("/company", { state: { notice: `"${job.title}" no longer takes applications.` } });
    } catch (err) {
      setState({ ...state, error: errorMessage(err) });
    }
  }

  return (
    <form onSubmit={submit} noValidate className="space-y-6">
      {state.error && <Alert tone="danger">{state.error}</Alert>}
      {job?.status === "approved" && !company.is_verified && (
        <Alert tone="info">This job is live. Saving changes sends it back for review, and it's hidden until it's approved again.</Alert>
      )}

      <Section title="The role">
        <Field label="Job title" htmlFor={`${id}-title`} error={f.title}>
          <Input id={`${id}-title`} maxLength={200} value={form.title} onChange={set("title")} invalid={Boolean(f.title)} placeholder="e.g. Finance Intern" />
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Type" htmlFor={`${id}-type`} error={f.role_type}>
            <Select id={`${id}-type`} value={form.role_type} onChange={set("role_type")}>
              {Object.entries(ROLE_TYPES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </Field>
          <Field label="Field" htmlFor={`${id}-cat`} error={f.category}>
            <Select id={`${id}-cat`} value={form.category} onChange={set("category")} invalid={Boolean(f.category)}>
              <option value="">Choose a field</option>
              {categories.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </Select>
          </Field>
          <Field label="Location" htmlFor={`${id}-loc`} error={f.location}>
            <Input id={`${id}-loc`} value={form.location} onChange={set("location")} placeholder="e.g. Juba, South Sudan" />
          </Field>
          <Field label="Where they'll work" htmlFor={`${id}-mode`} error={f.work_mode}>
            <Select id={`${id}-mode`} value={form.work_mode} onChange={set("work_mode")}>
              <option value="">Not stated</option>
              {Object.entries(WORK_MODES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </Field>
          <Field label="Hours" htmlFor={`${id}-hours`} error={f.employment_type}>
            <Select id={`${id}-hours`} value={form.employment_type} onChange={set("employment_type")}>
              <option value="">Not stated</option>
              {Object.entries(EMPLOYMENT_TYPES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
          </Field>
          <Field label="Pay" htmlFor={`${id}-paid`} error={f.is_paid}>
            <Select id={`${id}-paid`} value={form.is_paid} onChange={set("is_paid")}>
              <option value="">Not stated</option>
              <option value="true">Paid</option>
              <option value="false">Unpaid</option>
            </Select>
          </Field>
          {form.role_type === "internship" && (
            <Field label="Length in months" htmlFor={`${id}-dur`} error={f.duration_months}>
              <Input id={`${id}-dur`} type="number" min={1} max={24} value={form.duration_months} onChange={set("duration_months")} />
            </Field>
          )}
          <Field label="Application deadline" htmlFor={`${id}-dl`} error={f.application_deadline} hint="Leave empty to accept applications until you close the job.">
            <Input id={`${id}-dl`} type="datetime-local" value={form.application_deadline} onChange={set("application_deadline")} />
          </Field>
        </div>
        <Field label="Summary" htmlFor={`${id}-desc`} error={f.description} hint="A short paragraph shown at the top of the listing.">
          <Textarea id={`${id}-desc`} rows={4} value={form.description} onChange={set("description")} invalid={Boolean(f.description)} />
        </Field>
        {SECTION_FIELDS.map(([kind, label]) => (
          <Field key={kind} label={`${label} (optional)`} htmlFor={`${id}-${kind}`} hint={'One paragraph per line; start a line with "- " for a bullet point.'}>
            <Textarea id={`${id}-${kind}`} rows={3} value={form.sections[kind] || ""} onChange={(e) => setForm((x) => ({ ...x, sections: { ...x.sections, [kind]: e.target.value } }))} />
          </Field>
        ))}
      </Section>

      <Section title="Who can apply" intro="SimplyFind is for students and people who graduated in the last two years.">
        <div className="grid gap-5 sm:grid-cols-3">
          <Field label="Experience asked for" htmlFor={`${id}-exp`} error={f.experience_years_max}>
            <Select id={`${id}-exp`} value={form.experience_years_max} onChange={set("experience_years_max")}>
              <option value="0">None</option>
              <option value="1">Up to 1 year</option>
              <option value="2">Up to 2 years</option>
            </Select>
          </Field>
          <Field label="Graduating from" htmlFor={`${id}-gmin`} error={f.graduation_year_min}>
            <Select id={`${id}-gmin`} value={form.graduation_year_min} onChange={set("graduation_year_min")}>
              <option value="">Any year</option>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </Select>
          </Field>
          <Field label="Graduating up to" htmlFor={`${id}-gmax`} error={f.graduation_year_max}>
            <Select id={`${id}-gmax`} value={form.graduation_year_max} onChange={set("graduation_year_max")} invalid={Boolean(f.graduation_year_max)}>
              <option value="">Any year</option>
              {years.map((y) => <option key={y} value={y}>{y}</option>)}
            </Select>
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-brand" checked={form.accepts_minors} onChange={set("accepts_minors")} />
          Open to applicants under 18
        </label>
      </Section>

      <Section title="How people apply">
        <fieldset disabled={locked}>
          <legend className="sr-only">Application method</legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {[
              ["in_app", "On SimplyFind", "Applicants answer your questions and attach documents from their vault."],
              ["external", "On our website", "We link to your own application page."],
            ].map(([v, l, help]) => (
              <label key={v} className="flex cursor-pointer items-start gap-2 rounded-lg border border-border p-3 text-sm has-[:checked]:border-brand has-[:checked]:bg-brand-soft">
                <input type="radio" name={`${id}-method`} value={v} checked={form.application_method === v} onChange={set("application_method")} className="mt-0.5 accent-brand" />
                <span>
                  <span className="font-medium">{l}</span>
                  <span className="block text-muted">{help}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        {form.application_method === "external" ? (
          <Field label="Link to your application page" htmlFor={`${id}-url`} error={f.opportunity_url}>
            <Input id={`${id}-url`} type="url" placeholder="https://" value={form.opportunity_url} onChange={set("opportunity_url")} invalid={Boolean(f.opportunity_url)} />
          </Field>
        ) : locked ? (
          <div className="space-y-2">
            <p className="inline-flex items-center gap-1.5 text-sm text-muted">
              <Lock className="size-4" /> People have applied, so the questions are locked: every applicant answers the same ones.
            </p>
            <ol className="list-decimal space-y-1 pl-5 text-sm">
              {form.requirements.map((r, i) => <li key={i}>{r.label} <span className="text-muted">({QUESTION_KINDS[r.kind]}{r.required ? "" : ", optional"})</span></li>)}
            </ol>
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted">Applicants' profile (studies, skills, certificates) comes with every application. Add what else you need.</p>
            {f.requirements && <p className="text-xs text-danger">{f.requirements}</p>}
            {form.requirements.map((q, i) => (
              <QuestionEditor
                key={i}
                q={q}
                index={i}
                count={form.requirements.length}
                error={f[`q${i}`]}
                onChange={(nq) => setQuestions((list) => list.map((x, j) => (j === i ? nq : x)))}
                onMove={(d) => setQuestions((list) => {
                  const next = [...list];
                  [next[i], next[i + d]] = [next[i + d], next[i]];
                  return next;
                })}
                onRemove={() => setQuestions((list) => list.filter((_, j) => j !== i))}
              />
            ))}
            {form.requirements.length < 30 && (
              <Button type="button" variant="secondary" onClick={() => setQuestions((list) => [...list, { label: "", kind: "short_text", help_text: "", required: true, options: [] }])}>
                <Plus className="size-4" /> Add a question
              </Button>
            )}
          </div>
        )}
      </Section>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-2">
          <Button type="submit" size="lg" loading={state.busy}>{job ? "Save changes" : company.publishes_directly ? "Publish job" : "Send for review"}</Button>
          <Link to="/company" className="inline-flex h-12 items-center px-4 text-sm font-medium text-muted hover:text-text">Cancel</Link>
        </div>
        {job?.is_open && job.status === "approved" && (
          closing ? (
            <span className="inline-flex items-center gap-2 text-sm">
              Stop taking applications now?
              <Button type="button" variant="danger" size="sm" onClick={closeJob}>Close job</Button>
              <Button type="button" variant="ghost" size="sm" onClick={() => setClosing(false)}>Keep open</Button>
            </span>
          ) : (
            <Button type="button" variant="ghost" onClick={() => setClosing(true)}>Close this job</Button>
          )
        )}
      </div>
    </form>
  );
}

export default function JobForm() {
  const { id } = useParams();
  useTitle(id ? "Edit job" : "Post a job");
  const { data, loading, error } = useApi(
    (signal) => Promise.all([id ? companyApi.job(id, { signal }) : null, opportunitiesApi.categories({ signal })]).then(([job, categories]) => ({ job, categories })),
    [id],
  );
  if (loading && !data) return <Spinner />;
  if (error) return <Alert tone="danger">{errorMessage(error)}</Alert>;
  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/company" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-text"><ArrowLeft className="size-4" /> Jobs</Link>
      <h2 className="mb-6 text-2xl font-semibold">{id ? `Edit: ${data.job.title}` : "Post a job"}</h2>
      <Form job={data.job} categories={data.categories} />
    </div>
  );
}
