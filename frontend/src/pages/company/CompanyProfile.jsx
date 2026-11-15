import { useId, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Camera, ExternalLink } from "lucide-react";
import { COMPANY_SIZES, companyApi } from "../../api/company";
import { errorMessage, fieldErrors } from "../../api/client";
import { Alert, Button, Card, Field, Input, Select, Textarea } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { useTitle } from "../../lib/hooks";
import { useCompany } from "./CompanyLayout";

const FIELDS = ["name", "website", "industry", "location", "size", "contact_email", "description"];

export default function CompanyProfile() {
  useTitle("Company profile");
  const id = useId();
  const { company, setCompany } = useCompany();
  const { reload: reloadUser } = useAuth();
  const canEdit = company.my_permissions.manage_profile;
  const locked = company.status === "approved" || company.status === "suspended"; // name and website were checked at approval
  const [form, setForm] = useState(() => Object.fromEntries(FIELDS.map((k) => [k, company[k] || ""])));
  const [state, setState] = useState({ busy: false, error: null, fields: {}, saved: null });
  const fileRef = useRef(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function save(e) {
    e.preventDefault();
    setState({ busy: true, error: null, fields: {}, saved: null });
    const body = Object.fromEntries(FIELDS.filter((k) => !(locked && (k === "name" || k === "website"))).map((k) => [k, form[k].trim()]));
    try {
      const updated = await companyApi.update(body);
      setCompany(updated);
      reloadUser();
      setState({ busy: false, error: null, fields: {}, saved: updated.status === "pending" && company.status === "rejected" ? "Saved and sent for review again." : "Saved." });
    } catch (err) {
      const fields = fieldErrors(err);
      setState({ busy: false, fields, error: Object.keys(fields).length ? "Check the highlighted fields." : errorMessage(err), saved: null });
    }
  }

  async function uploadLogo(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setState({ ...state, busy: true, error: null, saved: null });
    try {
      setCompany(await companyApi.uploadLogo(file));
      reloadUser();
      setState({ busy: false, error: null, fields: {}, saved: "Logo updated." });
    } catch (err) {
      setState({ busy: false, error: fieldErrors(err).logo || errorMessage(err), fields: {}, saved: null });
    }
  }

  const f = state.fields;
  return (
    <Card className="mx-auto max-w-3xl p-6">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Company profile</h2>
        {company.status === "approved" && (
          <Link to={`/companies/${company.slug}`} className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline">
            See the public page <ExternalLink className="size-3.5" />
          </Link>
        )}
      </div>
      {!canEdit && <Alert tone="info" className="mb-4">Only owners and admins can change the company profile.</Alert>}
      <div className="mb-6 flex items-center gap-4">
        {company.logo_url ? (
          <img src={company.logo_url} alt="" className="size-20 rounded-xl border border-border object-contain p-1" />
        ) : (
          <span className="grid size-20 place-items-center rounded-xl bg-brand-soft text-3xl font-bold text-brand">{company.name.charAt(0)}</span>
        )}
        {canEdit && (
          <div>
            <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()} disabled={state.busy}>
              <Camera className="size-4" /> {company.logo_url ? "Change logo" : "Add a logo"}
            </Button>
            <p className="mt-1 text-xs text-muted">PNG or JPG, up to 2 MB. A square image works best.</p>
            <input ref={fileRef} type="file" accept="image/png,image/jpeg" className="hidden" onChange={uploadLogo} />
          </div>
        )}
      </div>
      <form onSubmit={save} className="space-y-5" noValidate>
        <fieldset disabled={!canEdit} className="space-y-5">
          {state.error && <Alert tone="danger">{state.error}</Alert>}
          <div className="grid gap-5 sm:grid-cols-2">
            <Field label="Company name" htmlFor={`${id}-name`} error={f.name} hint={locked ? "Checked at approval. Contact us to change it." : undefined}>
              <Input id={`${id}-name`} value={form.name} onChange={set("name")} readOnly={locked} invalid={Boolean(f.name)} />
            </Field>
            <Field label="Website" htmlFor={`${id}-web`} error={f.website} hint={locked ? "Checked at approval. Contact us to change it." : undefined}>
              <Input id={`${id}-web`} type="url" value={form.website} onChange={set("website")} readOnly={locked} invalid={Boolean(f.website)} />
            </Field>
            <Field label="Industry" htmlFor={`${id}-ind`} error={f.industry}>
              <Input id={`${id}-ind`} value={form.industry} onChange={set("industry")} />
            </Field>
            <Field label="Location" htmlFor={`${id}-loc`} error={f.location}>
              <Input id={`${id}-loc`} value={form.location} onChange={set("location")} />
            </Field>
            <Field label="Size" htmlFor={`${id}-size`} error={f.size}>
              <Select id={`${id}-size`} value={form.size} onChange={set("size")}>
                <option value="">Not stated</option>
                {COMPANY_SIZES.map((s) => <option key={s} value={s}>{s} people</option>)}
              </Select>
            </Field>
            <Field label="Contact email" htmlFor={`${id}-email`} error={f.contact_email} hint="Not shown publicly.">
              <Input id={`${id}-email`} type="email" value={form.contact_email} onChange={set("contact_email")} invalid={Boolean(f.contact_email)} />
            </Field>
          </div>
          <Field label="About the company" htmlFor={`${id}-desc`} error={f.description}>
            <Textarea id={`${id}-desc`} rows={5} value={form.description} onChange={set("description")} />
          </Field>
          {state.saved && <Alert tone="success">{state.saved}</Alert>}
          {canEdit && <Button type="submit" loading={state.busy}>Save</Button>}
        </fieldset>
      </form>
    </Card>
  );
}
