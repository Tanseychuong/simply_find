import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, SearchX, SlidersHorizontal, Search, X } from "lucide-react";
import { opportunitiesApi } from "../api/opportunities";
import OpportunityCard, { CardSkeleton } from "../components/opportunities/OpportunityCard";
import { Alert, Button, Container, EmptyState, Input, Select, cx } from "../components/ui";
import { ROLE_TYPES, WORK_MODES } from "../lib/format";
import { useApi, useDebounced, useTitle } from "../lib/hooks";
import { errorMessage } from "../api/client";

/*
  Every filter lives in the URL (?role_type=internship,entry_level&paid=true),
  so results can be shared and the back button works. The keys are the API's
  own filter names and are passed straight through.
*/
const PAGE_SIZE = 18;
const FILTER_KEYS = ["search", "category", "role_type", "work_mode", "paid", "graduation_year", "ordering"];
const ORDERINGS = { "": "Newest first", application_deadline: "Closing soonest" };

function useListParams() {
  const [params, setParams] = useSearchParams();
  const get = (k) => params.get(k) || "";
  const list = (k) => get(k).split(",").filter(Boolean);

  function update(changes) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      const value = Array.isArray(v) ? v.join(",") : v;
      if (value) next.set(k, value);
      else next.delete(k);
    }
    if (!("page" in changes)) next.delete("page"); // a new filter starts at page 1
    // Each filter or page is a history entry (Back undoes it); search-as-you-type
    // replaces, so Back doesn't step through every pause in typing.
    const typingOnly = Object.keys(changes).every((k) => k === "search");
    setParams(next, { replace: typingOnly });
  }
  return { params, get, list, update };
}

function CheckGroup({ legend, options, selected, onChange }) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-semibold">{legend}</legend>
      <div className="space-y-1.5">
        {Object.entries(options).map(([value, label]) => {
          const checked = selected.includes(value);
          return (
            <label key={value} className="flex cursor-pointer items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4 rounded border-border accent-brand"
                checked={checked}
                onChange={() => onChange(checked ? selected.filter((v) => v !== value) : [...selected, value])}
              />
              {label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

function Filters({ p, categories }) {
  const [year, setYear] = useState(p.get("graduation_year"));
  const urlYear = p.get("graduation_year");
  useEffect(() => {
    setYear(urlYear);
  }, [urlYear]);

  return (
    <div className="space-y-6">
      <CheckGroup legend="Type of role" options={ROLE_TYPES} selected={p.list("role_type")} onChange={(v) => p.update({ role_type: v })} />
      <CheckGroup legend="Where you work" options={WORK_MODES} selected={p.list("work_mode")} onChange={(v) => p.update({ work_mode: v })} />
      <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
        <input
          type="checkbox"
          className="size-4 rounded border-border accent-brand"
          checked={p.get("paid") === "true"}
          onChange={(e) => p.update({ paid: e.target.checked ? "true" : "" })}
        />
        Paid roles only
      </label>
      <div className="space-y-2">
        <label htmlFor="f-category" className="text-sm font-semibold">Field</label>
        <Select id="f-category" value={p.get("category")} onChange={(e) => p.update({ category: e.target.value })}>
          <option value="">All fields</option>
          {(categories || []).map((c) => (
            <option key={c.id} value={c.slug}>
              {c.name} ({c.live_count})
            </option>
          ))}
        </Select>
      </div>
      <form
        className="space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          p.update({ graduation_year: /^\d{4}$/.test(year) ? year : "" });
        }}
      >
        <label htmlFor="f-year" className="text-sm font-semibold">My graduation year</label>
        <div className="flex gap-2">
          <Input
            id="f-year"
            inputMode="numeric"
            maxLength={4}
            placeholder="e.g. 2026"
            value={year}
            onChange={(e) => setYear(e.target.value.replace(/\D/g, ""))}
            onBlur={() => year !== urlYear && p.update({ graduation_year: /^\d{4}$/.test(year) ? year : "" })}
          />
          <Button type="submit" variant="secondary">Apply</Button>
        </div>
        <p className="text-xs text-muted">Shows roles open to graduates of that year.</p>
      </form>
    </div>
  );
}

function Pagination({ page, count, onPage }) {
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  if (pages <= 1) return null;
  return (
    <nav className="mt-8 flex items-center justify-center gap-3" aria-label="Pages">
      <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        <ChevronLeft className="size-4" /> Previous
      </Button>
      <span className="text-sm text-muted">
        Page {page} of {pages}
      </span>
      <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next <ChevronRight className="size-4" />
      </Button>
    </nav>
  );
}

export default function Opportunities() {
  const p = useListParams();
  const [showFilters, setShowFilters] = useState(false);
  const [searchText, setSearchText] = useState(p.get("search"));
  const debouncedSearch = useDebounced(searchText);
  const urlSearch = p.get("search");

  // Typing searches as you go; a back/forward navigation resets the box.
  useEffect(() => {
    if (debouncedSearch.trim() !== urlSearch) p.update({ search: debouncedSearch.trim() });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);
  useEffect(() => {
    setSearchText((current) => (current.trim() === urlSearch ? current : urlSearch));
  }, [urlSearch]);

  const page = Math.max(1, parseInt(p.get("page"), 10) || 1);
  const query = Object.fromEntries(FILTER_KEYS.map((k) => [k, p.get(k)]));
  const queryKey = JSON.stringify(query) + page;

  const { data, loading, error } = useApi(
    (signal) => opportunitiesApi.list({ ...query, page, page_size: PAGE_SIZE }, { signal }),
    [queryKey],
  );
  const { data: categories } = useApi((signal) => opportunitiesApi.categories({ signal }), []);

  const category = categories?.find((c) => c.slug === p.get("category"));
  useTitle(category ? `${category.name} roles` : "Find roles");

  const activeCount = ["category", "role_type", "work_mode", "paid", "graduation_year"].filter((k) => p.get(k)).length;
  const results = data?.results || [];

  return (
    <Container className="py-8">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">{category ? `${category.name} roles` : "Find roles"}</h1>
        <p className="mt-1 text-muted">Internships, graduate programmes and entry-level jobs. Every listing is checked before it goes live.</p>
      </header>

      <div className="mb-6 flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1" role="search">
          <label htmlFor="search" className="sr-only">Search roles</label>
          <Search className="pointer-events-none absolute top-1/2 left-3 size-5 -translate-y-1/2 text-muted" aria-hidden />
          <Input id="search" type="search" value={searchText} onChange={(e) => setSearchText(e.target.value)} placeholder="Role, organisation or city" className="h-11 pl-10" />
        </div>
        <div className="flex gap-2">
          <label htmlFor="ordering" className="sr-only">Sort by</label>
          <Select id="ordering" className="h-11 sm:w-48" value={p.get("ordering")} onChange={(e) => p.update({ ordering: e.target.value })}>
            {Object.entries(ORDERINGS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          <Button variant="secondary" className="h-11 lg:hidden" onClick={() => setShowFilters((v) => !v)} aria-expanded={showFilters}>
            <SlidersHorizontal className="size-4" /> Filters{activeCount ? ` (${activeCount})` : ""}
          </Button>
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-[240px_1fr]">
        <aside className={cx("lg:block", showFilters ? "block" : "hidden")} aria-label="Filters">
          <div className="rounded-xl border border-border bg-surface p-4 lg:sticky lg:top-24 lg:border-0 lg:bg-transparent lg:p-0">
            <Filters p={p} categories={categories} />
            {activeCount > 0 && (
              <button
                type="button"
                className="mt-6 inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline"
                onClick={() => p.update({ category: "", role_type: "", work_mode: "", paid: "", graduation_year: "" })}
              >
                <X className="size-4" /> Clear filters
              </button>
            )}
          </div>
        </aside>

        <section aria-live="polite" aria-busy={loading}>
          {error ? (
            <Alert tone="danger">{errorMessage(error)}</Alert>
          ) : (
            <>
              {data && <p className="mb-4 text-sm text-muted">{data.count} role{data.count === 1 ? "" : "s"}</p>}
              {loading && !data ? (
                <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
                  {Array.from({ length: 6 }, (_, i) => <CardSkeleton key={i} />)}
                </div>
              ) : results.length === 0 ? (
                <EmptyState icon={SearchX} title="No roles match these filters">
                  Try fewer filters or a different search. New roles are added every few hours.
                </EmptyState>
              ) : (
                <div className={cx("grid gap-4 sm:grid-cols-2 xl:grid-cols-3", loading && "opacity-60")}>
                  {results.map((o) => <OpportunityCard key={o.id} opp={o} />)}
                </div>
              )}
              {data && <Pagination page={page} count={data.count} onPage={(n) => { p.update({ page: String(n) }); window.scrollTo(0, 0); }} />}
            </>
          )}
        </section>
      </div>
    </Container>
  );
}
