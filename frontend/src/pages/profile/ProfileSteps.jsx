import { useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { profileApi } from "../../api/profile";
import { opportunitiesApi } from "../../api/opportunities";
import { errorMessage, fieldErrors } from "../../api/client";
import TagInput from "../../components/profile/TagInput";
import { Alert, Button, Card, Field, Input, Select } from "../../components/ui";
import { useAuth } from "../../context/AuthContext";
import { COUNTRIES, LANGUAGES } from "../../lib/countries";
import { useApi, useTitle } from "../../lib/hooks";
import { STEP_PATHS, useProfile } from "./ProfileLayout";

const ORDER = ["about", "studies", "skills", "documents"];

/** Form state for one step, saved with PATCH /api/profile/, then on to the next step. */
function useStepForm(step, keys) {
  const { profile, setProfile } = useProfile();
  const { reload: reloadUser } = useAuth();
  const navigate = useNavigate();
  const [values, setValues] = useState(() => Object.fromEntries(keys.map((k) => [k, profile[k] ?? ""])));
  const [state, setState] = useState({ busy: false, error: null, fields: {} });

  const set = (key) => (e) => setValues((v) => ({ ...v, [key]: e?.target ? e.target.value : e }));

  async function save(e, toPayload = (v) => v) {
    e.preventDefault();
    setState({ busy: true, error: null, fields: {} });
    try {
      const updated = await profileApi.update(toPayload(values));
      setProfile(updated);
      if ("name" in values) reloadUser();
      const next = ORDER[ORDER.indexOf(step) + 1];
      navigate(next ? `/profile/${STEP_PATHS[next]}` : "/profile");
    } catch (err) {
      const fields = fieldErrors(err);
      setState({ busy: false, fields, error: Object.keys(fields).length ? "Check the highlighted fields." : errorMessage(err) });
      return;
    }
    setState({ busy: false, error: null, fields: {} });
  }
  return { values, set, save, state };
}

function StepCard({ title, intro, children, onSubmit, state, last }) {
  return (
    <Card className="p-4 sm:p-6">
      <h2 className="text-xl font-semibold">{title}</h2>
      {intro && <p className="mt-1 text-sm text-muted">{intro}</p>}
      <form onSubmit={onSubmit} noValidate className="mt-6 space-y-5">
        {state.error && <Alert tone="danger">{state.error}</Alert>}
        {children}
        <div className="flex justify-end border-t border-border pt-5">
          <Button type="submit" loading={state.busy}>{last ? "Save" : "Save and continue"}</Button>
        </div>
      </form>
    </Card>
  );
}

export function AboutStep() {
  useTitle("About you");
  const id = useId();
  const { values, set, save, state } = useStepForm("about", ["name", "date_of_birth", "country", "city", "phone"]);
  const f = state.fields;
  return (
    <StepCard
      title="About you"
      intro="Your date of birth only checks the 18+ rule some roles have. Hiring teams never see it."
      onSubmit={(e) => save(e, (v) => ({ ...v, name: v.name.trim(), date_of_birth: v.date_of_birth || null }))}
      state={state}
    >
      <Field label="Full name" htmlFor={`${id}-name`} error={f.name}>
        <Input id={`${id}-name`} autoComplete="name" value={values.name} onChange={set("name")} invalid={Boolean(f.name)} />
      </Field>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Date of birth" htmlFor={`${id}-dob`} error={f.date_of_birth}>
          <Input id={`${id}-dob`} type="date" autoComplete="bday" value={values.date_of_birth} onChange={set("date_of_birth")} invalid={Boolean(f.date_of_birth)} max={new Date().toISOString().slice(0, 10)} />
        </Field>
        <Field label="Phone (optional)" htmlFor={`${id}-phone`} error={f.phone} hint="Shared only once a hiring team shortlists you.">
          <Input id={`${id}-phone`} type="tel" autoComplete="tel" placeholder="+211 912 345 678" value={values.phone} onChange={set("phone")} invalid={Boolean(f.phone)} />
        </Field>
        <Field label="Country" htmlFor={`${id}-country`} error={f.country}>
          <Input id={`${id}-country`} list={`${id}-countries`} autoComplete="country-name" value={values.country} onChange={set("country")} invalid={Boolean(f.country)} />
          <datalist id={`${id}-countries`}>
            {COUNTRIES.map((c) => <option key={c} value={c} />)}
          </datalist>
        </Field>
        <Field label="City (optional)" htmlFor={`${id}-city`} error={f.city}>
          <Input id={`${id}-city`} autoComplete="address-level2" value={values.city} onChange={set("city")} invalid={Boolean(f.city)} />
        </Field>
      </div>
    </StepCard>
  );
}

export function StudiesStep() {
  useTitle("Your studies");
  const id = useId();
  const { values, set, save, state } = useStepForm("studies", ["status", "institution", "programme", "field", "graduation_year"]);
  const { data: categories } = useApi((signal) => opportunitiesApi.categories({ signal }), []);
  const f = state.fields;
  const thisYear = new Date().getFullYear();
  return (
    <StepCard
      title="Your studies"
      intro="Roles on SimplyFind are for students and people who graduated in the last two years."
      onSubmit={(e) =>
        save(e, (v) => ({ ...v, field: v.field || null, graduation_year: v.graduation_year ? Number(v.graduation_year) : null }))
      }
      state={state}
    >
      <fieldset>
        <legend className="mb-2 text-sm font-medium">Are you a student or a graduate?</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          {[
            ["student", "I'm still studying"],
            ["graduate", "I've graduated"],
          ].map(([value, label]) => (
            <label key={value} className="flex cursor-pointer items-center gap-2 rounded-lg border border-border p-3 text-sm has-[:checked]:border-brand has-[:checked]:bg-brand-soft">
              <input type="radio" name={`${id}-status`} value={value} checked={values.status === value} onChange={set("status")} className="accent-brand" />
              {label}
            </label>
          ))}
        </div>
        {f.status && <p className="mt-1 text-xs text-danger">{f.status}</p>}
      </fieldset>
      <Field label="School or university" htmlFor={`${id}-inst`} error={f.institution}>
        <Input id={`${id}-inst`} value={values.institution} onChange={set("institution")} placeholder="e.g. University of Juba" invalid={Boolean(f.institution)} />
      </Field>
      <Field label="Course or programme" htmlFor={`${id}-prog`} error={f.programme}>
        <Input id={`${id}-prog`} value={values.programme} onChange={set("programme")} placeholder="e.g. BSc Computer Science" invalid={Boolean(f.programme)} />
      </Field>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Field (optional)" htmlFor={`${id}-field`} error={f.field} hint="Helps us suggest roles.">
          <Select id={`${id}-field`} value={values.field || ""} onChange={set("field")}>
            <option value="">Choose a field</option>
            {(categories || []).map((c) => <option key={c.slug} value={c.slug}>{c.name}</option>)}
          </Select>
        </Field>
        <Field
          label={values.status === "graduate" ? "Year you graduated" : "Year you'll graduate"}
          htmlFor={`${id}-year`}
          error={f.graduation_year}
        >
          <Select id={`${id}-year`} value={values.graduation_year || ""} onChange={set("graduation_year")} invalid={Boolean(f.graduation_year)}>
            <option value="">Choose a year</option>
            {Array.from({ length: 13 }, (_, i) => thisYear + 6 - i).map((y) => <option key={y} value={y}>{y}</option>)}
          </Select>
        </Field>
      </div>
    </StepCard>
  );
}

export function SkillsStep() {
  useTitle("Your skills");
  const id = useId();
  const { values, set, save, state } = useStepForm("skills", ["headline", "skills", "languages"]);
  const f = state.fields;
  return (
    <StepCard title="Your skills" intro="What you can do and the languages you speak. Hiring teams can search for these." onSubmit={save} state={state}>
      <Field label="One line about you (optional)" htmlFor={`${id}-headline`} error={f.headline} hint="e.g. Final-year accounting student who loves spreadsheets">
        <Input id={`${id}-headline`} maxLength={160} value={values.headline} onChange={set("headline")} invalid={Boolean(f.headline)} />
      </Field>
      <Field label="Skills" htmlFor={`${id}-skills`} error={f.skills}>
        <TagInput id={`${id}-skills`} value={values.skills || []} onChange={set("skills")} max={20} placeholder="e.g. Excel, Python, Customer service" invalid={Boolean(f.skills)} />
      </Field>
      <Field label="Languages" htmlFor={`${id}-langs`} error={f.languages}>
        <TagInput id={`${id}-langs`} value={values.languages || []} onChange={set("languages")} max={10} suggestions={LANGUAGES} placeholder="e.g. English, Arabic" invalid={Boolean(f.languages)} />
      </Field>
    </StepCard>
  );
}
