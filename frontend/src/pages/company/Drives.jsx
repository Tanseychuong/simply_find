import { useId, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { CalendarDays, MapPin, Plus, QrCode } from "lucide-react";
import { companyApi, drivesApi } from "../../api/company";
import { errorMessage, fieldErrors } from "../../api/client";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, Spinner, Textarea } from "../../components/ui";
import { formatDate } from "../../lib/format";
import { useApi, useTitle } from "../../lib/hooks";
import { useCompany } from "./CompanyLayout";

export function DriveFields({ form, setForm, jobs, errors = {} }) {
  const id = useId();
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="space-y-5">
      <Field label="Name" htmlFor={`${id}-name`} error={errors.name} hint="e.g. University of Juba careers fair">
        <Input id={`${id}-name`} value={form.name} onChange={set("name")} invalid={Boolean(errors.name)} />
      </Field>
      <div className="grid gap-5 sm:grid-cols-3">
        <Field label="Where" htmlFor={`${id}-loc`} error={errors.location}>
          <Input id={`${id}-loc`} value={form.location} onChange={set("location")} placeholder="e.g. Main hall, Juba" />
        </Field>
        <Field label="Starts" htmlFor={`${id}-start`} error={errors.starts_on}>
          <Input id={`${id}-start`} type="date" min={today} value={form.starts_on} onChange={set("starts_on")} invalid={Boolean(errors.starts_on)} />
        </Field>
        <Field label="Ends" htmlFor={`${id}-end`} error={errors.ends_on}>
          <Input id={`${id}-end`} type="date" min={form.starts_on || today} value={form.ends_on} onChange={set("ends_on")} invalid={Boolean(errors.ends_on)} />
        </Field>
      </div>
      <Field label="Description (optional)" htmlFor={`${id}-desc`} error={errors.description} hint="Shown on the drive's public page.">
        <Textarea id={`${id}-desc`} rows={3} value={form.description} onChange={set("description")} />
      </Field>
      {jobs.length > 0 && (
        <fieldset>
          <legend className="mb-2 text-sm font-medium">Jobs to show on the drive's page</legend>
          <div className="space-y-1.5">
            {jobs.map((j) => (
              <label key={j.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="size-4 accent-brand"
                  checked={form.opportunities.includes(j.id)}
                  onChange={(e) => setForm({ ...form, opportunities: e.target.checked ? [...form.opportunities, j.id] : form.opportunities.filter((x) => x !== j.id) })}
                />
                {j.title} {j.status !== "approved" && <span className="text-xs text-muted">(not live yet)</span>}
              </label>
            ))}
          </div>
          {errors.opportunities && <p className="mt-1 text-xs text-danger">{errors.opportunities}</p>}
        </fieldset>
      )}
    </div>
  );
}

export const emptyDrive = { name: "", location: "", starts_on: "", ends_on: "", description: "", opportunities: [] };

export function drivePayload(form) {
  return {
    name: form.name.trim(), location: form.location.trim(), description: form.description.trim(),
    starts_on: form.starts_on || null, ends_on: form.ends_on || null, opportunities: form.opportunities,
  };
}

export default function Drives() {
  useTitle("Recruitment drives");
  const { company } = useCompany();
  const navigate = useNavigate();
  const { data, loading, error } = useApi(
    (signal) => Promise.all([drivesApi.mine({ signal }), companyApi.jobs({ signal })]).then(([drives, jobs]) => ({ drives, jobs })),
    [],
  );
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(emptyDrive);
  const [state, setState] = useState({ busy: false, error: null, fields: {} });

  if (company.status !== "approved") {
    return <Alert tone="info">Recruitment drives are available once your company is approved.</Alert>;
  }
  if (loading && !data) return <Spinner />;
  if (error) return <Alert tone="danger">{errorMessage(error)}</Alert>;

  async function create(e) {
    e.preventDefault();
    setState({ busy: true, error: null, fields: {} });
    try {
      const drive = await drivesApi.create(drivePayload(form));
      navigate(`/company/drives/${drive.id}`);
    } catch (err) {
      const fields = fieldErrors(err);
      setState({ busy: false, fields, error: Object.keys(fields).length ? "Check the highlighted fields." : errorMessage(err) });
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Recruitment drives</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            A careers fair or a campus visit. Each drive gets a QR code for your stand: students scan it, sign up and apply. At the desk,
            your team can sign students up and scan their documents for them.
          </p>
        </div>
        {!creating && <Button onClick={() => setCreating(true)}><Plus className="size-4" /> New drive</Button>}
      </div>

      {creating && (
        <Card className="p-6">
          <form onSubmit={create} noValidate className="space-y-5">
            <h3 className="text-lg font-semibold">New drive</h3>
            {state.error && <Alert tone="danger">{state.error}</Alert>}
            <DriveFields form={form} setForm={setForm} jobs={data.jobs} errors={state.fields} />
            <div className="flex gap-2">
              <Button type="submit" loading={state.busy} disabled={!form.name.trim()}>Create drive</Button>
              <Button type="button" variant="ghost" onClick={() => setCreating(false)}>Cancel</Button>
            </div>
          </form>
        </Card>
      )}

      {data.drives.length === 0 ? (
        !creating && <EmptyState icon={QrCode} title="No drives yet">Create one before your next careers fair.</EmptyState>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.drives.map((d) => (
            <Link key={d.id} to={`/company/drives/${d.id}`} className="block">
              <Card className="h-full p-5 transition-colors hover:border-brand">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold">{d.name}</h3>
                  <Badge tone={d.is_active ? "success" : "neutral"}>{d.is_active ? "Open" : "Closed"}</Badge>
                </div>
                <div className="mt-2 space-y-1 text-sm text-muted">
                  {d.location && <p className="flex items-center gap-1.5"><MapPin className="size-4" /> {d.location}</p>}
                  {d.starts_on && <p className="flex items-center gap-1.5"><CalendarDays className="size-4" /> {formatDate(d.starts_on)}{d.ends_on && d.ends_on !== d.starts_on ? ` to ${formatDate(d.ends_on)}` : ""}</p>}
                </div>
                <p className="mt-3 text-sm">
                  <strong>{d.registration_count}</strong> signed up · <strong>{d.claimed_count}</strong> claimed · code <span className="font-mono">{d.code}</span>
                </p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
