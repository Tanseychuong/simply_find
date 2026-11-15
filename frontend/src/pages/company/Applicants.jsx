import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { ArrowLeft, ChevronDown, Download, EyeOff, FileText, Mail, Phone, Printer, Search, Users } from "lucide-react";
import { BULK_STATUSES, HIRING_STATUSES, companyApi } from "../../api/company";
import { APPLICATION_STATUS, CHECK_STATUS, applicationsApi } from "../../api/profile";
import { opportunitiesApi } from "../../api/opportunities";
import { errorMessage, fieldErrors } from "../../api/client";
import { Alert, Badge, Button, Card, EmptyState, Input, Select, Spinner, Textarea, buttonClass, cx } from "../../components/ui";
import { formatDate } from "../../lib/format";
import { useApi, useDebounced, useTitle } from "../../lib/hooks";
import { safeExternalUrl } from "../../lib/urls";

const FILTER_KEYS = ["status", "graduation_year", "field", "applicant_status", "verified_certificates", "q"];

function ApplicantDetail({ app, onSaved }) {
  const a = app.applicant;
  const p = a.profile || {};
  const [note, setNote] = useState(app.company_note || "");
  const [state, setState] = useState({ busy: false, error: null, saved: false });

  async function save(changes) {
    setState({ busy: true, error: null, saved: false });
    try {
      onSaved(await companyApi.updateApplication(app.id, changes));
      setState({ busy: false, error: null, saved: true });
    } catch (err) {
      const f = fieldErrors(err);
      setState({ busy: false, error: f.status || f.company_note || errorMessage(err), saved: false });
    }
  }

  return (
    <div className="grid gap-6 border-t border-border p-5 lg:grid-cols-[1fr_300px]">
      <div className="space-y-5 text-sm">
        <section>
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Studies</h3>
          <p>
            {p.status === "graduate" ? "Graduated" : "Studying"} {p.programme || "(programme not given)"} at {p.institution || "(school not given)"}
            {p.graduation_year ? `, ${p.status === "graduate" ? "" : "graduating "}${p.graduation_year}` : ""}.
          </p>
          {p.field && <p className="text-muted">Field: {p.field}</p>}
          {(p.city || p.country) && <p className="text-muted">Based in {[p.city, p.country].filter(Boolean).join(", ")}</p>}
          {p.headline && <p className="mt-1 italic">"{p.headline}"</p>}
        </section>
        {(p.skills?.length > 0 || p.languages?.length > 0) && (
          <section>
            <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Skills and languages</h3>
            <div className="flex flex-wrap gap-1.5">
              {(p.skills || []).map((s) => <Badge key={s} tone="brand">{s}</Badge>)}
              {(p.languages || []).map((l) => <Badge key={l}>{l}</Badge>)}
            </div>
          </section>
        )}
        {a.credentials.length > 0 && (
          <section>
            <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Online certificates</h3>
            <ul className="space-y-1.5">
              {a.credentials.map((c, i) => {
                const st = CHECK_STATUS[c.check_status] || CHECK_STATUS.unchecked;
                const link = safeExternalUrl(c.url);
                return (
                  <li key={i} className="flex flex-wrap items-center gap-2">
                    {link ? <a href={link} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline">{c.title}</a> : c.title}
                    <Badge tone={st.tone}>{st.label}</Badge>
                  </li>
                );
              })}
            </ul>
          </section>
        )}
        <section>
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Answers</h3>
          {app.answers.length === 0 ? (
            <p className="text-muted">No questions were asked.</p>
          ) : (
            <dl className="space-y-3">
              {app.answers.map((ans) => (
                <div key={ans.id}>
                  <dt className="font-medium">{ans.label}</dt>
                  <dd className="mt-0.5 whitespace-pre-line text-muted">
                    {ans.kind === "file" ? (
                      ans.has_file ? (
                        <a href={applicationsApi.answerFileUrl(ans.id)} className="inline-flex items-center gap-1 text-brand hover:underline">
                          <FileText className="size-4" /> {ans.original_filename || "Download file"}
                        </a>
                      ) : "No file"
                    ) : ans.kind === "url" && safeExternalUrl(ans.value) ? (
                      <a href={safeExternalUrl(ans.value)} target="_blank" rel="noopener noreferrer nofollow" className="text-brand hover:underline break-all">{ans.value}</a>
                    ) : (
                      ans.value || "No answer"
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          <p className="mt-3 text-xs text-muted">The applicant can see when your team opens their files.</p>
        </section>
      </div>
      <aside className="space-y-4">
        <div className="rounded-lg bg-surface-2 p-4 text-sm">
          {a.contact_visible ? (
            <div className="space-y-1.5">
              <a href={`mailto:${a.email}`} className="flex items-center gap-2 text-brand hover:underline break-all"><Mail className="size-4 shrink-0" /> {a.email}</a>
              {a.phone && <a href={`tel:${a.phone}`} className="flex items-center gap-2 text-brand hover:underline"><Phone className="size-4" /> {a.phone}</a>}
            </div>
          ) : (
            <p className="flex items-start gap-2 text-muted"><EyeOff className="mt-0.5 size-4 shrink-0" /> Email and phone appear once you shortlist this applicant.</p>
          )}
        </div>
        <div className="space-y-1.5">
          <label htmlFor={`status-${app.id}`} className="text-sm font-medium">Status</label>
          <Select id={`status-${app.id}`} value={app.status} disabled={state.busy} onChange={(e) => save({ status: e.target.value })}>
            {HIRING_STATUSES.map((s) => <option key={s} value={s}>{APPLICATION_STATUS[s].label}</option>)}
          </Select>
          <p className="text-xs text-muted">The applicant is emailed when you change it.</p>
        </div>
        <div className="space-y-1.5">
          <label htmlFor={`note-${app.id}`} className="text-sm font-medium">Private note</label>
          <Textarea id={`note-${app.id}`} rows={3} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Only your team sees this." />
          <Button size="sm" variant="secondary" loading={state.busy} disabled={note === (app.company_note || "")} onClick={() => save({ company_note: note })}>Save note</Button>
        </div>
        {state.error && <Alert tone="danger">{state.error}</Alert>}
        {state.saved && <p className="text-xs text-success">Saved.</p>}
      </aside>
    </div>
  );
}

export default function Applicants() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const get = (k) => params.get(k) || "";
  const [q, setQ] = useState(get("q"));
  const debouncedQ = useDebounced(q);
  const [open, setOpen] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [bulk, setBulk] = useState({ status: "reviewing", busy: false, message: null, error: null });

  function update(changes) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) (v ? next.set(k, v) : next.delete(k));
    setParams(next, { replace: true });
  }
  useEffect(() => {
    if (debouncedQ.trim() !== get("q")) update({ q: debouncedQ.trim() });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQ]);

  const filters = Object.fromEntries(FILTER_KEYS.map((k) => [k, get(k)]));
  const key = JSON.stringify(filters);
  const { data: job } = useApi((signal) => companyApi.job(id, { signal }), [id]);
  const { data: categories } = useApi((signal) => opportunitiesApi.categories({ signal }), []);
  const { data, loading, error, setData, reload } = useApi((signal) => companyApi.applications(id, { ...filters, page_size: 100 }, { signal }), [id, key]);
  useTitle(job ? `Applicants: ${job.title}` : "Applicants");

  const apps = Array.isArray(data) ? data : data?.results || [];
  const total = Array.isArray(data) ? data.length : data?.count ?? apps.length;
  useEffect(() => setSelected(new Set()), [key]);

  const statuses = get("status").split(",").filter(Boolean);
  const filtering = FILTER_KEYS.some((k) => get(k));
  const toggleStatus = (s) => update({ status: (statuses.includes(s) ? statuses.filter((x) => x !== s) : [...statuses, s]).join(",") });
  const replaceApp = (na) => setData((d) => {
    const list = (Array.isArray(d) ? d : d.results).map((x) => (x.id === na.id ? { ...x, ...na } : x));
    return Array.isArray(d) ? list : { ...d, results: list };
  });

  async function applyBulk() {
    setBulk((b) => ({ ...b, busy: true, message: null, error: null }));
    try {
      const res = await companyApi.bulkStatus(id, [...selected], bulk.status);
      setBulk((b) => ({ ...b, busy: false, message: `${res.changed} applicant${res.changed === 1 ? "" : "s"} moved to "${APPLICATION_STATUS[bulk.status].label}" and emailed.` }));
      setSelected(new Set());
      reload();
    } catch (err) {
      const f = fieldErrors(err);
      setBulk((b) => ({ ...b, busy: false, error: f.ids || f.status || errorMessage(err) }));
    }
  }

  const exportParams = Object.fromEntries(Object.entries(filters).filter(([, v]) => v));
  const thisYear = new Date().getFullYear();

  return (
    <div>
      <Link to="/company" className="mb-4 inline-flex items-center gap-1 text-sm text-muted hover:text-text"><ArrowLeft className="size-4" /> Jobs</Link>
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-2xl font-semibold">{job?.title || "Applicants"}</h2>
          <p className="text-sm text-muted">{total} applicant{total === 1 ? "" : "s"}{filtering ? " match these filters" : ""}</p>
        </div>
        <div className="flex gap-2">
          <a href={companyApi.exportUrl(id, "csv", exportParams)} className={buttonClass({ variant: "secondary", size: "sm" })}><Download className="size-4" /> CSV</a>
          <a href={companyApi.exportUrl(id, "print", exportParams)} target="_blank" rel="noopener" className={buttonClass({ variant: "secondary", size: "sm" })}><Printer className="size-4" /> Print</a>
        </div>
      </div>

      <Card className="mb-4 space-y-4 p-4">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Status">
          {HIRING_STATUSES.map((s) => (
            <button
              key={s}
              type="button"
              aria-pressed={statuses.includes(s)}
              onClick={() => toggleStatus(s)}
              className={cx("rounded-full border px-3 py-1 text-sm", statuses.includes(s) ? "border-brand bg-brand-soft text-brand-strong" : "border-border text-muted hover:text-text")}
            >
              {APPLICATION_STATUS[s].label}
            </button>
          ))}
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative sm:col-span-2 lg:col-span-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted" aria-hidden />
            <Input aria-label="Search by name, school or programme" placeholder="Name, school or programme" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" />
          </div>
          <Select aria-label="Graduation year" value={get("graduation_year")} onChange={(e) => update({ graduation_year: e.target.value })}>
            <option value="">Any graduation year</option>
            {Array.from({ length: 9 }, (_, i) => thisYear + 4 - i).map((y) => <option key={y} value={y}>{y}</option>)}
          </Select>
          <Select aria-label="Field" value={get("field")} onChange={(e) => update({ field: e.target.value })}>
            <option value="">Any field</option>
            {(categories || []).map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
          </Select>
          <Select aria-label="Student or graduate" value={get("applicant_status")} onChange={(e) => update({ applicant_status: e.target.value })}>
            <option value="">Students and graduates</option>
            <option value="student">Students</option>
            <option value="graduate">Graduates</option>
          </Select>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-brand" checked={get("verified_certificates") === "true"} onChange={(e) => update({ verified_certificates: e.target.checked ? "true" : "" })} />
          Only applicants with a certificate verified with its issuer
        </label>
      </Card>

      {selected.size > 0 && (
        <div className="sticky top-16 z-10 mb-4 flex flex-wrap items-center gap-2 rounded-xl border border-brand/30 bg-brand-soft p-3 text-sm">
          <strong>{selected.size} selected</strong>
          <span className="text-muted">Move to</span>
          <Select aria-label="New status" value={bulk.status} onChange={(e) => setBulk((b) => ({ ...b, status: e.target.value }))} className="h-9 w-auto">
            {BULK_STATUSES.map((s) => <option key={s} value={s}>{APPLICATION_STATUS[s].label}</option>)}
          </Select>
          <Button size="sm" loading={bulk.busy} onClick={applyBulk}>Apply and email them</Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>Clear</Button>
        </div>
      )}
      {bulk.message && <Alert tone="success" className="mb-4">{bulk.message}</Alert>}
      {bulk.error && <Alert tone="danger" className="mb-4">{bulk.error}</Alert>}

      {loading && !data ? (
        <Spinner />
      ) : error ? (
        <Alert tone="danger">{errorMessage(error)}</Alert>
      ) : apps.length === 0 ? (
        <EmptyState icon={Users} title={filtering ? "No applicants match" : "No applicants yet"}>
          {filtering ? "Try fewer filters." : "Applications will appear here as they arrive."}
        </EmptyState>
      ) : (
        <Card className="divide-y divide-border overflow-hidden">
          <label className="flex items-center gap-3 bg-surface-2 px-5 py-2 text-xs font-medium text-muted">
            <input
              type="checkbox"
              className="size-4 accent-brand"
              checked={selected.size === apps.length}
              onChange={(e) => setSelected(e.target.checked ? new Set(apps.map((x) => x.id)) : new Set())}
            />
            Select all {apps.length}
          </label>
          {apps.map((app) => {
            const st = APPLICATION_STATUS[app.status];
            const p = app.applicant.profile || {};
            const isOpen = open === app.id;
            return (
              <div key={app.id}>
                <div className="flex items-center gap-3 px-5 py-4">
                  <input
                    type="checkbox"
                    className="size-4 shrink-0 accent-brand"
                    aria-label={`Select ${app.applicant.name}`}
                    checked={selected.has(app.id)}
                    onChange={() => setSelected((s) => {
                      const n = new Set(s);
                      n.has(app.id) ? n.delete(app.id) : n.add(app.id);
                      return n;
                    })}
                  />
                  <button type="button" onClick={() => setOpen(isOpen ? null : app.id)} className="flex min-w-0 flex-1 items-center gap-3 text-left" aria-expanded={isOpen}>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium">{app.applicant.name}</p>
                      <p className="truncate text-xs text-muted">
                        {[p.programme, p.institution, p.graduation_year].filter(Boolean).join(" · ") || "Profile not filled in"} · applied {formatDate(app.submitted_at)}
                      </p>
                    </div>
                    {app.applicant.credentials.some((c) => c.check_status === "verified") && <Badge tone="success" className="hidden sm:inline-flex">Verified certificate</Badge>}
                    <Badge tone={st.tone}>{st.label}</Badge>
                    <ChevronDown className={cx("size-4 shrink-0 text-muted transition-transform", isOpen && "rotate-180")} aria-hidden />
                  </button>
                </div>
                {isOpen && <ApplicantDetail app={app} onSaved={replaceApp} />}
              </div>
            );
          })}
        </Card>
      )}
    </div>
  );
}
