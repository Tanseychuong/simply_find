import { useEffect, useId, useState } from "react";
import { ChevronDown, Plus } from "lucide-react";
import { FILTERS } from "../../lib/filters";
import { Button, Input, cx } from "../ui";

/*
  The filter sidebar (desktop) and drawer (mobile). `p` is the page's URL
  helper: p.get(key), p.list(key), p.update({key: value}).
*/
const SHOW_FIRST = 6;

function Section({ title, count, defaultOpen = true, children }) {
  return (
    <details open={defaultOpen} className="group border-b border-border py-4 first:pt-0">
      <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-semibold [&::-webkit-details-marker]:hidden">
        <span>
          {title}
          {count > 0 && <span className="ml-2 rounded-full bg-brand-soft px-1.5 text-xs text-brand-strong">{count}</span>}
        </span>
        <ChevronDown className="size-4 text-muted transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="mt-3">{children}</div>
    </details>
  );
}

function Check({ type = "checkbox", name, checked, onChange, children, extra }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 py-1 text-sm">
      <input type={type} name={name} className="size-4 shrink-0 border-border accent-brand" checked={checked} onChange={onChange} />
      <span className="flex-1">{children}</span>
      {extra !== undefined && <span className="text-xs text-muted">{extra}</span>}
    </label>
  );
}

function MultiOptions({ p, fkey, options }) {
  const [showAll, setShowAll] = useState(false);
  const selected = p.list(fkey);
  const visible = showAll ? options : options.slice(0, SHOW_FIRST);
  // Keep selected options visible even when the list is folded.
  const hiddenSelected = showAll ? [] : options.slice(SHOW_FIRST).filter((o) => selected.includes(o.value));
  return (
    <div>
      {[...visible, ...hiddenSelected].map((o) => {
        const checked = selected.includes(o.value);
        return (
          <Check
            key={o.value}
            checked={checked}
            extra={o.count}
            onChange={() => p.update({ [fkey]: checked ? selected.filter((v) => v !== o.value) : [...selected, o.value] })}
          >
            {o.label}
          </Check>
        );
      })}
      {options.length > SHOW_FIRST && (
        <button type="button" className="mt-1 text-sm font-medium text-brand hover:underline" onClick={() => setShowAll((v) => !v)}>
          {showAll ? "Show fewer" : `Show all ${options.length}`}
        </button>
      )}
    </div>
  );
}

function SingleOptions({ p, fkey, options, anyLabel }) {
  const name = `${fkey}-${useId()}`; // unique per copy: the sidebar and the mobile drawer can both be in the page
  const current = p.get(fkey);
  return (
    <div>
      <Check type="radio" name={name} checked={!current} onChange={() => p.update({ [fkey]: "" })}>{anyLabel}</Check>
      {options.map((o) => (
        <Check key={o.value} type="radio" name={name} checked={current === o.value} onChange={() => p.update({ [fkey]: o.value })}>
          {o.label}
        </Check>
      ))}
    </div>
  );
}

function AddPlace({ p }) {
  const id = useId();
  const [text, setText] = useState("");
  function add(e) {
    e.preventDefault();
    const place = text.trim().replace(/,/g, " ").slice(0, 60);
    if (!place) return;
    const current = p.list("location");
    if (!current.some((v) => v.toLowerCase() === place.toLowerCase()) && current.length < 5) {
      p.update({ location: [...current, place] });
    }
    setText("");
  }
  return (
    <form onSubmit={add} className="mt-2 flex gap-2">
      <label htmlFor={id} className="sr-only">Add a city or country</label>
      <Input id={id} value={text} onChange={(e) => setText(e.target.value)} placeholder="City or country" className="h-9" />
      <Button type="submit" variant="secondary" size="sm" className="h-9" aria-label="Add place">
        <Plus className="size-4" />
      </Button>
    </form>
  );
}

function GraduationYear({ p }) {
  const id = useId();
  const urlYear = p.get("graduation_year");
  const [year, setYear] = useState(urlYear);
  useEffect(() => {
    setYear(urlYear);
  }, [urlYear]);
  const commit = () => year !== urlYear && p.update({ graduation_year: /^\d{4}$/.test(year) ? year : "" });
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        commit();
      }}
      className="space-y-1.5"
    >
      <div className="flex gap-2">
        <label htmlFor={id} className="sr-only">Graduation year</label>
        <Input
          id={id}
          inputMode="numeric"
          maxLength={4}
          placeholder="e.g. 2026"
          value={year}
          onChange={(e) => setYear(e.target.value.replace(/\D/g, ""))}
          onBlur={commit}
          className="h-9"
        />
        <Button type="submit" variant="secondary" size="sm" className="h-9">Apply</Button>
      </div>
      <p className="text-xs text-muted">Roles open to graduates of that year.</p>
    </form>
  );
}

const asOptions = (obj) => Object.entries(obj).map(([value, label]) => ({ value, label }));

export default function FilterPanel({ p, categories, locations }) {
  const byKey = Object.fromEntries(FILTERS.map((f) => [f.key, f]));
  const roleTypes = p.list("role_type");
  const showDuration = roleTypes.length === 0 || roleTypes.includes("internship");

  // Places with counts, plus any place in the URL that isn't in the list (typed in).
  const selectedPlaces = p.list("location");
  const placeOptions = (locations || []).map((l) => ({ value: l.name, label: l.name, count: l.count }));
  for (const place of selectedPlaces) {
    if (!placeOptions.some((o) => o.value.toLowerCase() === place.toLowerCase())) placeOptions.unshift({ value: place, label: place });
  }
  const categoryOptions = (categories || []).map((c) => ({ value: c.slug, label: c.name, count: c.live_count }));
  const toggles = FILTERS.filter((f) => f.kind === "toggle");
  const countOf = (key) => p.list(key).length;

  return (
    <div>
      <Section title="Type of role" count={countOf("role_type")}>
        <MultiOptions p={p} fkey="role_type" options={asOptions(byKey.role_type.options)} />
      </Section>
      <Section title="Career level" count={countOf("career_level")}>
        <MultiOptions p={p} fkey="career_level" options={asOptions(byKey.career_level.options)} />
      </Section>
      <Section title="Industry" count={countOf("category")}>
        <MultiOptions p={p} fkey="category" options={categoryOptions} />
      </Section>
      <Section title="Location" count={countOf("location")}>
        <MultiOptions p={p} fkey="location" options={placeOptions} />
        <AddPlace p={p} />
      </Section>
      <Section title="Where you work" count={countOf("work_mode")}>
        <MultiOptions p={p} fkey="work_mode" options={asOptions(byKey.work_mode.options)} />
      </Section>
      <Section title="Full-time or part-time" count={countOf("employment_type")}>
        <MultiOptions p={p} fkey="employment_type" options={asOptions(byKey.employment_type.options)} />
      </Section>
      <Section title="Deadline" count={p.get("deadline") ? 1 : 0}>
        <SingleOptions p={p} fkey="deadline" options={asOptions(byKey.deadline.options)} anyLabel="Any deadline" />
      </Section>
      <Section title="Date posted" count={p.get("posted_within") ? 1 : 0} defaultOpen={false}>
        <SingleOptions p={p} fkey="posted_within" options={asOptions(byKey.posted_within.options)} anyLabel="Any time" />
      </Section>
      {showDuration && (
        <Section title="Internship length" count={countOf("duration")} defaultOpen={false}>
          <MultiOptions p={p} fkey="duration" options={asOptions(byKey.duration.options)} />
        </Section>
      )}
      <Section title="Pay and more" count={toggles.filter((f) => p.get(f.key) === "true").length}>
        {toggles.map((f) => (
          <Check key={f.key} checked={p.get(f.key) === "true"} onChange={(e) => p.update({ [f.key]: e.target.checked ? "true" : "" })}>
            {f.label}
          </Check>
        ))}
      </Section>
      <Section title="Graduation year" count={p.get("graduation_year") ? 1 : 0} defaultOpen={false}>
        <GraduationYear p={p} />
      </Section>
    </div>
  );
}

export function FilterChips({ chips, onRemove, onClear }) {
  if (!chips.length) return null;
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      {chips.map((c) => (
        <button
          key={`${c.key}:${c.value}`}
          type="button"
          onClick={() => onRemove(c)}
          className={cx("inline-flex items-center gap-1 rounded-full border border-brand/30 bg-brand-soft px-3 py-1 text-xs font-medium text-brand-strong hover:border-brand")}
          aria-label={`Remove filter: ${c.label}`}
        >
          {c.label} <span aria-hidden>×</span>
        </button>
      ))}
      <button type="button" onClick={onClear} className="text-xs font-medium text-muted hover:text-text hover:underline">
        Clear all
      </button>
    </div>
  );
}
