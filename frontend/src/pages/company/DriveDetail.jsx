import { useId, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Check, Copy, Download, FileUp, MailCheck, UserPlus } from "lucide-react";
import { companyApi, drivesApi } from "../../api/company";
import { DOCUMENT_KINDS } from "../../api/profile";
import { errorMessage, fieldErrors } from "../../api/client";
import { checkFile } from "../../components/profile/DocumentUpload";
import { Alert, Badge, Button, Card, Field, Input, Select, Spinner, buttonClass } from "../../components/ui";
import { formatDate } from "../../lib/format";
import { COUNTRIES } from "../../lib/countries";
import { useApi, useTitle } from "../../lib/hooks";
import { DriveFields, drivePayload } from "./Drives";

const emptySignup = { name: "", email: "", institution: "", programme: "", graduation_year: "", status: "", phone: "", country: "" };

/** The desk: a team member signs a student up, with the student's spoken consent. */
function DeskSignup({ driveId, onAdded }) {
  const id = useId();
  const [form, setForm] = useState(emptySignup);
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState({ busy: false, error: null, fields: {} });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const thisYear = new Date().getFullYear();

  async function submit(e) {
    e.preventDefault();
    setState({ busy: true, error: null, fields: {} });
    const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, typeof v === "string" ? v.trim() : v]).filter(([, v]) => v !== ""));
    try {
      const reg = await drivesApi.signUp(driveId, { ...body, consent: true });
      onAdded(reg);
      setForm(emptySignup);
      setConsent(false);
      setState({ busy: false, error: null, fields: {} });
    } catch (err) {
      const fields = fieldErrors(err);
      setState({ busy: false, fields, error: fields.consent || (Object.keys(fields).length ? "Check the highlighted fields." : errorMessage(err)) });
    }
  }

  const f = state.fields;
  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      {state.error && <Alert tone="danger">{state.error}</Alert>}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Student's full name" htmlFor={`${id}-name`} error={f.name}>
          <Input id={`${id}-name`} value={form.name} onChange={set("name")} invalid={Boolean(f.name)} />
        </Field>
        <Field label="Student's email" htmlFor={`${id}-email`} error={f.email} hint="They get a link to set a password and claim the account.">
          <Input id={`${id}-email`} type="email" value={form.email} onChange={set("email")} invalid={Boolean(f.email)} />
        </Field>
        <Field label="School or university" htmlFor={`${id}-inst`} error={f.institution}>
          <Input id={`${id}-inst`} value={form.institution} onChange={set("institution")} />
        </Field>
        <Field label="Course or programme" htmlFor={`${id}-prog`} error={f.programme}>
          <Input id={`${id}-prog`} value={form.programme} onChange={set("programme")} />
        </Field>
        <Field label="Student or graduate" htmlFor={`${id}-status`} error={f.status}>
          <Select id={`${id}-status`} value={form.status} onChange={set("status")}>
            <option value="">Not asked</option>
            <option value="student">Student</option>
            <option value="graduate">Graduate</option>
          </Select>
        </Field>
        <Field label="Graduation year" htmlFor={`${id}-year`} error={f.graduation_year}>
          <Select id={`${id}-year`} value={form.graduation_year} onChange={set("graduation_year")}>
            <option value="">Not asked</option>
            {Array.from({ length: 10 }, (_, i) => thisYear + 5 - i).map((y) => <option key={y} value={y}>{y}</option>)}
          </Select>
        </Field>
        <Field label="Phone (optional)" htmlFor={`${id}-phone`} error={f.phone}>
          <Input id={`${id}-phone`} type="tel" value={form.phone} onChange={set("phone")} placeholder="+211 ..." invalid={Boolean(f.phone)} />
        </Field>
        <Field label="Country (optional)" htmlFor={`${id}-country`} error={f.country}>
          <Input id={`${id}-country`} list={`${id}-countries`} value={form.country} onChange={set("country")} />
          <datalist id={`${id}-countries`}>{COUNTRIES.map((c) => <option key={c} value={c} />)}</datalist>
        </Field>
      </div>
      <label className="flex items-start gap-3 rounded-lg bg-accent-soft p-4 text-sm">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 size-4 accent-brand" />
        <span>
          The student agreed to be signed up to SimplyFind and to have their documents scanned. If they don't claim the account within 14
          days, it's deleted with everything in it.
        </span>
      </label>
      <Button type="submit" loading={state.busy} disabled={!consent || !form.name.trim() || !form.email.trim()}>
        <UserPlus className="size-4" /> Sign up and email the claim link
      </Button>
    </form>
  );
}

function DeskScan({ driveId, reg, onUploaded }) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [kind, setKind] = useState("transcript");
  const [state, setState] = useState({ busy: false, error: null });

  async function upload(e) {
    e.preventDefault();
    const problem = checkFile(file);
    if (problem) return setState({ busy: false, error: problem });
    setState({ busy: true, error: null });
    try {
      await drivesApi.deskDocument(driveId, reg.id, { file, kind, title: `${DOCUMENT_KINDS[kind]} (scanned at the desk)` });
      onUploaded();
      setFile(null);
      setOpen(false);
      setState({ busy: false, error: null });
    } catch (err) {
      setState({ busy: false, error: fieldErrors(err).file || errorMessage(err) });
    }
  }

  if (!open) {
    return <Button variant="ghost" size="sm" onClick={() => setOpen(true)}><FileUp className="size-4" /> Scan a document</Button>;
  }
  return (
    <form onSubmit={upload} className="mt-3 w-full space-y-2 rounded-lg bg-surface-2 p-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        <Select aria-label="Document type" value={kind} onChange={(e) => setKind(e.target.value)} className="h-9 sm:w-48">
          {Object.entries(DOCUMENT_KINDS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </Select>
        <input
          type="file"
          accept=".pdf,.jpg,.jpeg,.png"
          capture="environment"
          aria-label="File or photo"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-brand-soft file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-brand-strong"
        />
      </div>
      {state.error && <p className="text-xs text-danger">{state.error}</p>}
      <div className="flex gap-2">
        <Button type="submit" size="sm" loading={state.busy} disabled={!file}>Upload</Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setOpen(false)}>Cancel</Button>
      </div>
      <p className="text-xs text-muted">On a phone this opens the camera. Only possible on the day of the signup, before the student claims the account.</p>
    </form>
  );
}

function Registrations({ driveId, active, onChange }) {
  const { data, loading, error, setData, reload } = useApi((signal) => drivesApi.students(driveId, { signal }), [driveId]);
  const [resent, setResent] = useState({});
  const [message, setMessage] = useState(null);

  return (
    <>
      {active ? (
        <Card className="p-6">
          <h3 className="mb-1 text-lg font-semibold">Signup desk</h3>
          <p className="mb-5 text-sm text-muted">For students without a phone or data. Ask for their consent before you start.</p>
          <DeskSignup driveId={driveId} onAdded={(reg) => {
            setData((d) => [reg, ...(d || [])]);
            onChange();
            setMessage(`${reg.student_name} is signed up. We emailed ${reg.student_email} a link to claim the account.`);
          }} />
          {message && <Alert tone="success" className="mt-4">{message}</Alert>}
        </Card>
      ) : (
        <Alert tone="info">The drive is closed, so the signup desk is off. Reopen it to sign students up.</Alert>
      )}
      <Card className="p-6">
        <h3 className="mb-4 text-lg font-semibold">Students from this drive</h3>
        {loading && !data ? (
          <Spinner />
        ) : error ? (
          <Alert tone="danger">{errorMessage(error)}</Alert>
        ) : data.length === 0 ? (
          <p className="text-sm text-muted">No one yet. Students who scan the QR code and sign up appear here too.</p>
        ) : (
          <ul className="divide-y divide-border">
            {data.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="font-medium">{r.student_name}</p>
                  <p className="truncate text-xs text-muted">
                    {r.student_email} · {r.method === "assisted" ? `signed up at the desk${r.registered_by_name ? ` by ${r.registered_by_name}` : ""}` : "signed up with the QR code"} · {formatDate(r.created_at)} · {r.document_count} document{r.document_count === 1 ? "" : "s"}
                  </p>
                </div>
                {r.method === "assisted" && (
                  r.claimed_at ? (
                    <Badge tone="success">Claimed</Badge>
                  ) : (
                    <>
                      <Badge tone="accent">Not claimed yet</Badge>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={resent[r.id]}
                        onClick={async () => {
                          try {
                            await drivesApi.resendClaim(driveId, r.id);
                            setResent((s) => ({ ...s, [r.id]: true }));
                          } catch (err) {
                            setMessage(errorMessage(err));
                          }
                        }}
                      >
                        {resent[r.id] ? <><MailCheck className="size-4" /> Sent</> : "Resend email"}
                      </Button>
                      <DeskScan driveId={driveId} reg={r} onUploaded={() => { reload(); onChange(); }} />
                    </>
                  )
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </>
  );
}

export default function DriveDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data, loading, error, setData, reload: reloadDrive } = useApi(
    (signal) => Promise.all([drivesApi.get(id, { signal }), companyApi.jobs({ signal })]).then(([drive, jobs]) => ({ drive, jobs })),
    [id],
  );
  const [editing, setEditing] = useState(null);
  const [state, setState] = useState({ busy: false, error: null, fields: {} });
  const [copied, setCopied] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useTitle(data?.drive?.name || "Drive");

  if (loading && !data) return <Spinner />;
  if (error) return <Alert tone="danger">{errorMessage(error)}</Alert>;
  const { drive, jobs } = data;

  async function save(changes) {
    setState({ busy: true, error: null, fields: {} });
    try {
      const updated = await drivesApi.update(drive.id, changes);
      setData((d) => ({ ...d, drive: updated }));
      setEditing(null);
      setState({ busy: false, error: null, fields: {} });
    } catch (err) {
      const fields = fieldErrors(err);
      setState({ busy: false, fields, error: Object.keys(fields).length ? "Check the highlighted fields." : errorMessage(err) });
    }
  }

  return (
    <div className="space-y-6">
      <Link to="/company/drives" className="inline-flex items-center gap-1 text-sm text-muted hover:text-text"><ArrowLeft className="size-4" /> Drives</Link>
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <Card className="p-6">
          {editing ? (
            <form onSubmit={(e) => { e.preventDefault(); save(drivePayload(editing)); }} noValidate className="space-y-5">
              {state.error && <Alert tone="danger">{state.error}</Alert>}
              <DriveFields form={editing} setForm={setEditing} jobs={jobs} errors={state.fields} />
              <div className="flex gap-2">
                <Button type="submit" loading={state.busy}>Save</Button>
                <Button type="button" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button>
              </div>
            </form>
          ) : (
            <>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-2xl font-semibold">{drive.name}</h2>
                  <p className="mt-1 text-sm text-muted">
                    {[drive.location, drive.starts_on && formatDate(drive.starts_on), drive.ends_on && drive.ends_on !== drive.starts_on && `to ${formatDate(drive.ends_on)}`].filter(Boolean).join(" · ")}
                  </p>
                </div>
                <Badge tone={drive.is_active ? "success" : "neutral"}>{drive.is_active ? "Open" : "Closed"}</Badge>
              </div>
              {drive.description && <p className="mt-4 text-sm whitespace-pre-line">{drive.description}</p>}
              <p className="mt-4 text-sm"><strong>{drive.registration_count}</strong> signed up · <strong>{drive.claimed_count}</strong> claimed</p>
              <p className="mt-2 text-sm text-muted">
                Jobs on the drive page: {drive.opportunities.length ? jobs.filter((j) => drive.opportunities.includes(j.id)).map((j) => j.title).join(", ") : "none"}
              </p>
              {state.error && <Alert tone="danger" className="mt-4">{state.error}</Alert>}
              <div className="mt-5 flex flex-wrap gap-2">
                <Button variant="secondary" size="sm" onClick={() => setEditing({
                  name: drive.name, location: drive.location || "", starts_on: drive.starts_on || "", ends_on: drive.ends_on || "",
                  description: drive.description || "", opportunities: drive.opportunities,
                })}>Edit</Button>
                <Button variant="secondary" size="sm" loading={state.busy} onClick={() => save({ is_active: !drive.is_active })}>
                  {drive.is_active ? "Close the drive" : "Reopen the drive"}
                </Button>
                {confirmDelete ? (
                  <span className="inline-flex items-center gap-2 text-sm">
                    Delete this drive?
                    <Button variant="danger" size="sm" onClick={async () => { await drivesApi.remove(drive.id); navigate("/company/drives"); }}>Delete</Button>
                    <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>Keep</Button>
                  </span>
                ) : (
                  <Button variant="ghost" size="sm" onClick={() => setConfirmDelete(true)}>Delete</Button>
                )}
              </div>
            </>
          )}
        </Card>
        <Card className="p-6 text-center">
          <img src={drivesApi.qrUrl(drive.id)} alt={`QR code for ${drive.public_url}`} className="mx-auto size-48 rounded-lg bg-white p-2" />
          <p className="mt-3 font-mono text-lg font-semibold tracking-widest">{drive.code}</p>
          <p className="mt-1 text-xs break-all text-muted">{drive.public_url}</p>
          <div className="mt-4 flex justify-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(drive.public_url);
                  setCopied(true);
                } catch {
                  setCopied(false);
                }
              }}
            >
              {copied ? <Check className="size-4" /> : <Copy className="size-4" />} {copied ? "Copied" : "Copy link"}
            </Button>
            <a href={drivesApi.qrUrl(drive.id)} download={`simplyfind-drive-${drive.code}.png`} className={buttonClass({ variant: "secondary", size: "sm" })}>
              <Download className="size-4" /> QR code
            </a>
          </div>
          <p className="mt-3 text-xs text-muted">Print it for your stand and posters.</p>
        </Card>
      </div>
      {/* The counts on the drive card follow the desk. */}
      <Registrations driveId={drive.id} active={drive.is_active} onChange={reloadDrive} />
    </div>
  );
}
