import { useId, useState } from "react";
import { Award, Download, ExternalLink, FileText, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { CHECK_STATUS, CREDENTIAL_PROVIDERS, DOCUMENT_KINDS, profileApi } from "../../api/profile";
import { errorMessage, fieldErrors } from "../../api/client";
import DocumentUpload, { formatSize } from "../../components/profile/DocumentUpload";
import { Alert, Badge, Button, ButtonLink, Card, EmptyState, Field, Input, Select, Spinner } from "../../components/ui";
import { formatDate } from "../../lib/format";
import { useApi, useTitle } from "../../lib/hooks";
import { safeExternalUrl } from "../../lib/urls";
import { useProfile } from "./ProfileLayout";

function ConfirmDelete({ onConfirm, label }) {
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!asking) {
    return (
      <Button variant="ghost" size="sm" onClick={() => setAsking(true)} aria-label={`Delete ${label}`}>
        <Trash2 className="size-4" />
      </Button>
    );
  }
  return (
    <span className="inline-flex items-center gap-1">
      <Button
        variant="danger"
        size="sm"
        loading={busy}
        onClick={async () => {
          setBusy(true);
          try {
            await onConfirm();
          } finally {
            setBusy(false);
            setAsking(false);
          }
        }}
      >
        Delete
      </Button>
      <Button variant="ghost" size="sm" onClick={() => setAsking(false)}>Keep</Button>
    </span>
  );
}

function DocumentRow({ doc, onChange, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(doc.title);
  const [error, setError] = useState(null);

  async function rename(e) {
    e.preventDefault();
    try {
      onChange(await profileApi.renameDocument(doc.id, title.trim()));
      setEditing(false);
      setError(null);
    } catch (err) {
      setError(fieldErrors(err).title || errorMessage(err));
    }
  }

  return (
    <li className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center">
      <FileText className="hidden size-8 shrink-0 text-brand sm:block" aria-hidden />
      <div className="min-w-0 flex-1">
        {editing ? (
          <form onSubmit={rename} className="flex gap-2">
            <label htmlFor={`doc-${doc.id}`} className="sr-only">Name</label>
            <Input id={`doc-${doc.id}`} value={title} maxLength={120} onChange={(e) => setTitle(e.target.value)} className="h-9" autoFocus />
            <Button type="submit" size="sm" className="h-9" disabled={!title.trim()}>Save</Button>
            <Button type="button" variant="ghost" size="sm" className="h-9" onClick={() => setEditing(false)}>Cancel</Button>
          </form>
        ) : (
          <p className="truncate font-medium">{doc.title}</p>
        )}
        {error && <p className="mt-1 text-xs text-danger">{error}</p>}
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
          <Badge>{DOCUMENT_KINDS[doc.kind] || doc.kind}</Badge>
          <span>{formatSize(doc.size)}</span>
          <span>Added {formatDate(doc.created_at)}</span>
          {doc.uploaded_by_someone_else && <span>Scanned for you at a recruitment drive</span>}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <a href={profileApi.documentFileUrl(doc.id)} className={"inline-flex h-8 items-center gap-1.5 rounded-lg px-3 text-sm font-medium hover:bg-surface-2"} aria-label={`Download ${doc.title}`}>
          <Download className="size-4" /> <span className="sm:hidden">Download</span>
        </a>
        {!editing && (
          <Button variant="ghost" size="sm" onClick={() => setEditing(true)} aria-label={`Rename ${doc.title}`}>
            <Pencil className="size-4" />
          </Button>
        )}
        <ConfirmDelete label={doc.title} onConfirm={onDelete} />
      </div>
    </li>
  );
}

function Vault({ onCountChange }) {
  const { data: docs, loading, error, setData } = useApi((signal) => profileApi.documents({ signal }), []);
  const [adding, setAdding] = useState(false);
  const [notice, setNotice] = useState(null);

  const update = (next) => {
    setData(next);
    onCountChange();
  };

  return (
    <Card className="p-6">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Document vault</h2>
          <p className="mt-1 text-sm text-muted">
            Transcripts, certificates and your CV, stored privately. When you apply, the hiring team gets a copy of the ones you pick, and
            you can see when they open them.
          </p>
        </div>
        {!adding && (
          <Button onClick={() => setAdding(true)}>
            <Plus className="size-4" /> Add a document
          </Button>
        )}
      </div>
      {notice && <Alert tone="success" className="my-3">{notice}</Alert>}
      {adding && (
        <div className="my-4">
          <DocumentUpload
            onCancel={() => setAdding(false)}
            onUploaded={(doc) => {
              update([doc, ...(docs || [])]);
              setAdding(false);
              setNotice(`"${doc.title}" was scanned and added to your vault.`);
            }}
          />
        </div>
      )}
      {loading && !docs ? (
        <Spinner />
      ) : error ? (
        <Alert tone="danger">{errorMessage(error)}</Alert>
      ) : docs.length === 0 ? (
        !adding && <EmptyState icon={FileText} title="No documents yet">Add your transcript first: most applications ask for it.</EmptyState>
      ) : (
        <ul className="divide-y divide-border">
          {docs.map((d) => (
            <DocumentRow
              key={d.id}
              doc={d}
              onChange={(nd) => setData(docs.map((x) => (x.id === nd.id ? nd : x)))}
              onDelete={async () => {
                await profileApi.deleteDocument(d.id);
                setNotice(null);
                update(docs.filter((x) => x.id !== d.id));
              }}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

function AddCredential({ onAdded, onCancel }) {
  const id = useId();
  const [form, setForm] = useState({ url: "", title: "", provider: "", issuer: "", issued_on: "" });
  const [state, setState] = useState({ busy: false, error: null, fields: {} });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setState({ busy: true, error: null, fields: {} });
    const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v.trim()).map(([k, v]) => [k, v.trim()]));
    try {
      onAdded(await profileApi.addCredential(payload));
    } catch (err) {
      const fields = fieldErrors(err);
      setState({ busy: false, fields, error: Object.keys(fields).length ? null : errorMessage(err) });
    }
  }

  const f = state.fields;
  return (
    <form onSubmit={submit} className="space-y-4 rounded-xl border border-border bg-surface-2/50 p-4" noValidate>
      {state.error && <Alert tone="danger">{state.error}</Alert>}
      <Field label="Link to the certificate" htmlFor={`${id}-url`} error={f.url} hint="The public page on Coursera, edX, Credly or LinkedIn Learning, or an Open Badge link.">
        <Input id={`${id}-url`} type="url" placeholder="https://" value={form.url} onChange={set("url")} invalid={Boolean(f.url)} autoFocus />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Certificate name" htmlFor={`${id}-title`} error={f.title} hint="Not needed for Open Badges: we read it from the badge.">
          <Input id={`${id}-title`} value={form.title} onChange={set("title")} placeholder="e.g. Google Data Analytics" invalid={Boolean(f.title)} />
        </Field>
        <Field label="Where from (optional)" htmlFor={`${id}-provider`} error={f.provider} hint="We work it out from the link if you leave this.">
          <Select id={`${id}-provider`} value={form.provider} onChange={set("provider")}>
            <option value="">Work it out from the link</option>
            {Object.entries(CREDENTIAL_PROVIDERS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </Field>
        <Field label="Issued by (optional)" htmlFor={`${id}-issuer`} error={f.issuer}>
          <Input id={`${id}-issuer`} value={form.issuer} onChange={set("issuer")} placeholder="e.g. Google" />
        </Field>
        <Field label="Date issued (optional)" htmlFor={`${id}-date`} error={f.issued_on}>
          <Input id={`${id}-date`} type="date" value={form.issued_on} onChange={set("issued_on")} />
        </Field>
      </div>
      <div className="flex gap-2">
        <Button type="submit" loading={state.busy} disabled={!form.url.trim()}>Add and check</Button>
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </form>
  );
}

function Credentials({ onCountChange }) {
  const { data: creds, loading, error, setData } = useApi((signal) => profileApi.credentials({ signal }), []);
  const [adding, setAdding] = useState(false);
  const [checking, setChecking] = useState(null);

  const update = (next) => {
    setData(next);
    onCountChange();
  };

  return (
    <Card className="p-6">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">Online certificates</h2>
          <p className="mt-1 text-sm text-muted">Courses and badges from Coursera, edX, Credly, LinkedIn Learning and Open Badges. We check each link.</p>
        </div>
        {!adding && (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            <Plus className="size-4" /> Add a certificate
          </Button>
        )}
      </div>
      {adding && (
        <div className="my-4">
          <AddCredential
            onCancel={() => setAdding(false)}
            onAdded={(c) => {
              update([c, ...(creds || [])]);
              setAdding(false);
            }}
          />
        </div>
      )}
      {loading && !creds ? (
        <Spinner />
      ) : error ? (
        <Alert tone="danger">{errorMessage(error)}</Alert>
      ) : creds.length === 0 ? (
        !adding && <p className="py-4 text-sm text-muted">No certificates yet.</p>
      ) : (
        <ul className="divide-y divide-border">
          {creds.map((c) => {
            const status = CHECK_STATUS[c.check_status] || CHECK_STATUS.unchecked;
            const link = safeExternalUrl(c.url);
            return (
              <li key={c.id} className="flex flex-col gap-3 py-4 sm:flex-row sm:items-center">
                <Award className="hidden size-8 shrink-0 text-accent sm:block" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{c.title}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                    <Badge tone={status.tone}>{status.label}</Badge>
                    <span>{CREDENTIAL_PROVIDERS[c.provider] || c.provider}</span>
                    {c.issuer && <span>{c.issuer}</span>}
                    {c.issued_on && <span>{formatDate(c.issued_on)}</span>}
                  </div>
                  {c.check_status === "failed" && c.check_detail && <p className="mt-1 text-xs text-danger">{c.check_detail}</p>}
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {link && (
                    <a href={link} target="_blank" rel="noopener noreferrer" className="inline-flex h-8 items-center rounded-lg px-3 hover:bg-surface-2" aria-label={`Open ${c.title}`}>
                      <ExternalLink className="size-4" />
                    </a>
                  )}
                  {c.check_status !== "verified" && (
                    <Button
                      variant="ghost"
                      size="sm"
                      loading={checking === c.id}
                      aria-label={`Check ${c.title} again`}
                      onClick={async () => {
                        setChecking(c.id);
                        try {
                          const nc = await profileApi.recheckCredential(c.id);
                          setData(creds.map((x) => (x.id === nc.id ? nc : x)));
                        } finally {
                          setChecking(null);
                        }
                      }}
                    >
                      {checking !== c.id && <RefreshCw className="size-4" />}
                    </Button>
                  )}
                  <ConfirmDelete
                    label={c.title}
                    onConfirm={async () => {
                      await profileApi.deleteCredential(c.id);
                      update(creds.filter((x) => x.id !== c.id));
                    }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export default function DocumentsStep() {
  useTitle("Documents and certificates");
  const { reloadProfile, profile } = useProfile();
  const done = profile.progress.steps.find((s) => s.key === "documents")?.done;
  return (
    <div className="space-y-6">
      <Vault onCountChange={reloadProfile} />
      <Credentials onCountChange={reloadProfile} />
      {done && (
        <div className="flex justify-end">
          <ButtonLink to="/profile">Done</ButtonLink>
        </div>
      )}
    </div>
  );
}
