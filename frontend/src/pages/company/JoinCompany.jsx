import { useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { ClipboardCheck, FileCheck2, QrCode, ShieldCheck, Users } from "lucide-react";
import { COMPANY_SIZES, companyApi } from "../../api/company";
import { errorCodeOf, errorMessage, fieldErrors } from "../../api/client";
import { Alert, Button, ButtonLink, Card, Container, Field, Input, Select, Textarea } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { useTitle } from "../../lib/hooks";

const FEATURES = [
  { icon: FileCheck2, title: "Verified documents", body: "Applicants attach transcripts and certificates from their vault. Online certificates are checked with the issuer." },
  { icon: ClipboardCheck, title: "Your own questions", body: "Ask for a CV, a transcript, a link or a short answer. Filter applicants by graduation year, field and verified certificates." },
  { icon: QrCode, title: "Campus recruitment drives", body: "A QR code for your stand, and a desk to sign students up and scan their documents on the day." },
  { icon: Users, title: "Your whole team", body: "Invite recruiters and admins. Every team member signs in with two-step sign-in." },
];

function RegisterForm() {
  const id = useId();
  const { user, reload } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", website: "", industry: "", location: "", size: "", contact_email: user.email, description: "" });
  const [accept, setAccept] = useState(false);
  const [state, setState] = useState({ busy: false, error: null, fields: {} });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setState({ busy: true, error: null, fields: {} });
    const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim()]));
    try {
      await companyApi.register({ ...body, accept_terms: accept });
      await reload();
      navigate("/company");
    } catch (err) {
      const fields = fieldErrors(err);
      setState({
        busy: false,
        fields,
        error: errorCodeOf(err) === "email_not_verified" ? "Confirm your email first: use the bar at the top of the page." : fields.accept_terms || (Object.keys(fields).length ? "Check the highlighted fields." : errorMessage(err)),
      });
    }
  }

  const f = state.fields;
  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      {state.error && <Alert tone="danger">{state.error}</Alert>}
      <Field label="Company name" htmlFor={`${id}-name`} error={f.name} hint="As it's registered. It can't be changed after approval.">
        <Input id={`${id}-name`} value={form.name} onChange={set("name")} invalid={Boolean(f.name)} autoComplete="organization" />
      </Field>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Website" htmlFor={`${id}-web`} error={f.website} hint="Helps us check the company.">
          <Input id={`${id}-web`} type="url" placeholder="https://" value={form.website} onChange={set("website")} invalid={Boolean(f.website)} />
        </Field>
        <Field label="Industry" htmlFor={`${id}-ind`} error={f.industry}>
          <Input id={`${id}-ind`} value={form.industry} onChange={set("industry")} placeholder="e.g. Banking" invalid={Boolean(f.industry)} />
        </Field>
        <Field label="Location" htmlFor={`${id}-loc`} error={f.location}>
          <Input id={`${id}-loc`} value={form.location} onChange={set("location")} placeholder="e.g. Juba, South Sudan" invalid={Boolean(f.location)} />
        </Field>
        <Field label="Size" htmlFor={`${id}-size`} error={f.size}>
          <Select id={`${id}-size`} value={form.size} onChange={set("size")}>
            <option value="">Choose</option>
            {COMPANY_SIZES.map((s) => <option key={s} value={s}>{s} people</option>)}
          </Select>
        </Field>
      </div>
      <Field label="Contact email" htmlFor={`${id}-email`} error={f.contact_email} hint="Where we write about your account. Not shown publicly.">
        <Input id={`${id}-email`} type="email" value={form.contact_email} onChange={set("contact_email")} invalid={Boolean(f.contact_email)} />
      </Field>
      <Field label="About the company" htmlFor={`${id}-desc`} error={f.description} hint="Shown on your public company page.">
        <Textarea id={`${id}-desc`} rows={4} value={form.description} onChange={set("description")} invalid={Boolean(f.description)} />
      </Field>
      <label className="flex items-start gap-3 rounded-lg bg-surface-2 p-4 text-sm">
        <input type="checkbox" checked={accept} onChange={(e) => setAccept(e.target.checked)} className="mt-0.5 size-4 accent-brand" />
        <span>
          I may act for this company, and we'll use applicants' information only to recruit for the role they applied to. We won't
          ask applicants for fees, and we'll keep their documents confidential.
        </span>
      </label>
      <Button type="submit" size="lg" loading={state.busy} disabled={!accept || !form.name.trim()}>Register the company</Button>
      <p className="text-xs text-muted">We review every company before it can post, usually within two working days.</p>
    </form>
  );
}

export default function JoinCompany() {
  useTitle("Hire on SimplyFind");
  const { user } = useAuth();

  let panel;
  if (!user) {
    panel = (
      <div className="space-y-3">
        <p className="text-sm text-muted">Create a personal account first (it takes a minute), then register your company.</p>
        <ButtonLink to="/register?next=/companies/join" className="w-full">Create an account</ButtonLink>
        <ButtonLink to="/login?next=/companies/join" variant="secondary" className="w-full">I have an account</ButtonLink>
      </div>
    );
  } else if (user.company) {
    panel = (
      <div className="space-y-3">
        <p className="text-sm">You're on the team at <strong>{user.company.name}</strong>.</p>
        <ButtonLink to="/company" className="w-full">Open the company dashboard</ButtonLink>
      </div>
    );
  } else if (!user.email_verified) {
    panel = <Alert tone="warning">Confirm your email address first. Use the bar at the top of the page to send the link again.</Alert>;
  } else {
    panel = <RegisterForm />;
  }

  return (
    <>
      <section className="border-b border-border bg-gradient-to-b from-brand-soft/60 to-bg">
        <Container className="py-14">
          <h1 className="max-w-3xl text-4xl font-bold tracking-tight">Hire students and recent graduates, without the paperwork</h1>
          <p className="mt-4 max-w-2xl text-lg text-muted">
            Post internships, graduate programmes and entry-level roles. Applicants come with their studies, skills and documents in one place.
          </p>
        </Container>
      </section>
      <Container className="grid gap-10 py-12 lg:grid-cols-[1fr_480px]">
        <div className="grid content-start gap-4 sm:grid-cols-2">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <Card key={title} className="p-5">
              <Icon className="size-6 text-brand" aria-hidden />
              <h2 className="mt-3 font-semibold">{title}</h2>
              <p className="mt-1 text-sm text-muted">{body}</p>
            </Card>
          ))}
          <Card className="p-5 sm:col-span-2">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 size-5 text-brand" aria-hidden />
              <p className="text-sm text-muted">
                Applicants' email and phone stay hidden until you shortlist them, and they can see when your team opens their files.
                It keeps applications fair, and protects students.
              </p>
            </div>
          </Card>
        </div>
        <Card className="self-start p-6">
          <h2 className="mb-4 text-xl font-semibold">{user?.company ? "Your company" : "Register your company"}</h2>
          {panel}
        </Card>
      </Container>
    </>
  );
}
