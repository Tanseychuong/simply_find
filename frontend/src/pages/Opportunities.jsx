import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ChevronLeft, ChevronRight, Search, SearchX, SlidersHorizontal, X } from "lucide-react";
import { opportunitiesApi } from "../api/opportunities";
import { errorMessage } from "../api/client";
import FilterPanel, { FilterChips } from "../components/opportunities/FilterPanel";
import OpportunityCard, { CardSkeleton } from "../components/opportunities/OpportunityCard";
import { Alert, Button, Container, EmptyState, Input, Select, cx } from "../components/ui";
import { FILTER_KEYS, activeChips } from "../lib/filters";
import { useApi, useDebounced, useTitle } from "../lib/hooks";

/*
  Every filter lives in the URL (?role_type=internship&deadline=week), so
  results can be shared and Back undoes the last change. The keys are the
  API's own filter names (lib/filters.js) and are passed straight through.
*/
const PAGE_SIZE = 18;
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

function Pagination({ page, count, onPage }) {
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  if (pages <= 1) return null;
  return (
    <nav className="mt-8 flex items-center justify-center gap-3" aria-label="Pages">
      <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        <ChevronLeft className="size-4" /> Previous
      </Button>
      <span className="text-sm text-muted">Page {page} of {pages}</span>
      <Button variant="secondary" size="sm" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next <ChevronRight className="size-4" />
      </Button>
    </nav>
  );
}

/** Full-screen filter sheet on phones and tablets. */
function FilterDrawer({ open, onClose, count, children }) {
  useEffect(() => {
    if (!open) return undefined;
    const esc = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", esc);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", esc);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex flex-col bg-surface lg:hidden" role="dialog" aria-modal="true" aria-label="Filters">
      <div className="flex h-14 items-center justify-between border-b border-border px-4">
        <h2 className="font-semibold">Filters</h2>
        <button type="button" onClick={onClose} className="rounded-lg p-2 text-muted hover:bg-surface-2" aria-label="Close filters">
          <X className="size-5" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-4 py-4">{children}</div>
      <div className="border-t border-border p-4">
        <Button className="w-full" size="lg" onClick={onClose}>
          {count === undefined ? "Show roles" : `Show ${count} role${count === 1 ? "" : "s"}`}
        </Button>
      </div>
    </div>
  );
}

export default function Opportunities() {
  const p = useListParams();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const closeDrawer = useCallback(() => setDrawerOpen(false), []);
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
  const query = Object.fromEntries(["search", "ordering", ...FILTER_KEYS].map((k) => [k, p.get(k)]));
  const queryKey = JSON.stringify(query) + page;

  const { data, loading, error } = useApi(
    (signal) => opportunitiesApi.list({ ...query, page, page_size: PAGE_SIZE }, { signal }),
    [queryKey],
  );
  const { data: categories } = useApi((signal) => opportunitiesApi.categories({ signal }), []);
  const { data: locations } = useApi((signal) => opportunitiesApi.locations({ signal }), []);

  const onlyCategory = p.list("category").length === 1 ? categories?.find((c) => c.slug === p.get("category")) : null;
  const heading = onlyCategory ? `${onlyCategory.name} roles` : "Find roles";
  useTitle(heading);

  const chips = activeChips(p.params, { categories: categories || [] });
  const removeChip = (chip) => {
    const f = chip.key;
    const values = p.list(f).filter((v) => v !== chip.value);
    p.update({ [f]: values.length && chip.value !== p.get(f) ? values : "" });
  };
  const clearAll = () => p.update(Object.fromEntries(FILTER_KEYS.map((k) => [k, ""])));
  const results = data?.results || [];
  const panel = <FilterPanel p={p} categories={categories} locations={locations} />;

  return (
    <Container className="py-8">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight">{heading}</h1>
        <p className="mt-1 text-muted">Internships, graduate programmes and entry-level jobs. Every listing is checked before it goes live.</p>
      </header>

      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
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
          <Button variant="secondary" className="h-11 shrink-0 lg:hidden" onClick={() => setDrawerOpen(true)}>
            <SlidersHorizontal className="size-4" /> Filters{chips.length ? ` (${chips.length})` : ""}
          </Button>
        </div>
      </div>

      <div className="grid gap-8 lg:grid-cols-[260px_1fr]">
        <aside className="hidden lg:block" aria-label="Filters">
          {/* Full height, not a sticky inner scroller: with few results that box got cut off. */}
          {panel}
        </aside>
        <FilterDrawer open={drawerOpen} onClose={closeDrawer} count={data?.count}>
          {panel}
        </FilterDrawer>

        <section aria-live="polite" aria-busy={loading} className="min-w-0">
          <FilterChips chips={chips} onRemove={removeChip} onClear={clearAll} />
          {error ? (
            <Alert tone="danger">{errorMessage(error)}</Alert>
          ) : (
            <>
              {data && <p className="mb-4 text-sm text-muted">{data.count} role{data.count === 1 ? "" : "s"}</p>}
              {loading && !data ? (
                <div className="grid grid-cols-1 gap-3">
                  {Array.from({ length: 6 }, (_, i) => <CardSkeleton key={i} />)}
                </div>
              ) : results.length === 0 ? (
                <EmptyState
                  icon={SearchX}
                  title="No roles match these filters"
                  action={chips.length ? <Button variant="secondary" onClick={clearAll}>Clear all filters</Button> : null}
                >
                  Try fewer filters or a different search. New roles are added every few hours.
                </EmptyState>
              ) : (
                <div className={cx("grid grid-cols-1 gap-3", loading && "opacity-60")}>
                  {results.map((o) => <OpportunityCard key={o.id} opp={o} />)}
                </div>
              )}
              {data && (
                <Pagination
                  page={page}
                  count={data.count}
                  onPage={(n) => {
                    p.update({ page: String(n) });
                    window.scrollTo(0, 0);
                  }}
                />
              )}
            </>
          )}
        </section>
      </div>
    </Container>
  );
}
