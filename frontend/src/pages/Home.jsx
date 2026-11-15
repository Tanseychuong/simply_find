import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, FileCheck2, FolderLock, Search, ShieldCheck, Sparkles } from "lucide-react";
import { opportunitiesApi } from "../api/opportunities";
import OpportunityCard, { CardSkeleton } from "../components/opportunities/OpportunityCard";
import { Button, ButtonLink, Card, Container, Input } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { ROLE_TYPES, compactNumber } from "../lib/format";
import { useApi, useTitle } from "../lib/hooks";

const QUICK_TYPES = ["internship", "graduate_programme", "entry_level"];

function Hero() {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const { data: stats } = useApi((signal) => opportunitiesApi.stats({ signal }), []);

  function submit(e) {
    e.preventDefault();
    navigate(q.trim() ? `/opportunities?search=${encodeURIComponent(q.trim())}` : "/opportunities");
  }

  return (
    <section className="border-b border-border bg-gradient-to-b from-brand-soft/60 to-bg dark:from-surface">
      <Container className="py-14 sm:py-20">
        <div className="max-w-3xl">
          <p className="mb-4 inline-flex items-center gap-2 rounded-full border border-brand/20 bg-surface px-3 py-1 text-xs font-medium text-brand-strong">
            <Sparkles className="size-3.5" aria-hidden /> For students and recent graduates
          </p>
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl">
            Find your first role. <span className="text-brand">Apply without the paperwork.</span>
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-muted">
            Internships, graduate programmes and entry-level jobs in one place. Keep your transcripts and certificates
            on SimplyFind and attach them to any application in a click.
          </p>
          <form onSubmit={submit} className="mt-8 flex flex-col gap-2 sm:flex-row" role="search">
            <label htmlFor="hero-search" className="sr-only">Search roles</label>
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-5 -translate-y-1/2 text-muted" aria-hidden />
              <Input
                id="hero-search"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Role, organisation or city"
                className="h-12 pl-10 text-base"
              />
            </div>
            <Button type="submit" size="lg">Search roles</Button>
          </form>
          <div className="mt-4 flex flex-wrap gap-2 text-sm">
            {QUICK_TYPES.map((t) => (
              <Link
                key={t}
                to={`/opportunities?role_type=${t}`}
                className="rounded-full border border-border bg-surface px-3 py-1 text-muted hover:border-brand hover:text-brand"
              >
                {ROLE_TYPES[t]}s
              </Link>
            ))}
          </div>
        </div>
        {stats && (
          <dl className="mt-12 grid max-w-2xl grid-cols-3 gap-4">
            {[
              ["Open roles", stats.live],
              ["Added this week", stats.added_this_week],
              ["Organisations", stats.organizations],
            ].map(([label, n]) => (
              <div key={label}>
                <dt className="text-sm text-muted">{label}</dt>
                <dd className="text-2xl font-semibold sm:text-3xl">{compactNumber(n)}</dd>
              </div>
            ))}
          </dl>
        )}
      </Container>
    </section>
  );
}

function LatestRoles() {
  const { data, loading } = useApi((signal) => opportunitiesApi.list({ page_size: 6 }, { signal }), []);
  const results = data?.results || [];
  if (!loading && results.length === 0) return null;
  return (
    <section>
      <Container className="py-14">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold">Latest roles</h2>
            <p className="mt-1 text-sm text-muted">Checked by our team before they go live.</p>
          </div>
          <Link to="/opportunities" className="inline-flex items-center gap-1 text-sm font-medium text-brand hover:underline">
            See all <ArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
        <div className="grid grid-cols-1 gap-3">
          {loading ? Array.from({ length: 6 }, (_, i) => <CardSkeleton key={i} />) : results.map((o) => <OpportunityCard key={o.id} opp={o} />)}
        </div>
      </Container>
    </section>
  );
}

function Categories() {
  const { data } = useApi((signal) => opportunitiesApi.categories({ signal }), []);
  const cats = (data || []).filter((c) => c.live_count > 0);
  if (!cats.length) return null;
  return (
    <section className="border-y border-border bg-surface">
      <Container className="py-14">
        <h2 className="text-2xl font-semibold">Browse by field</h2>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {cats.map((c) => (
            <Link
              key={c.id}
              to={`/opportunities?category=${c.slug}`}
              className="group rounded-xl border border-border p-4 transition-colors hover:border-brand hover:bg-brand-soft/40"
            >
              <p className="font-medium group-hover:text-brand">{c.name}</p>
              <p className="mt-1 text-sm text-muted">
                {c.live_count} open role{c.live_count === 1 ? "" : "s"}
              </p>
            </Link>
          ))}
        </div>
      </Container>
    </section>
  );
}

const STEPS = [
  { icon: FileCheck2, title: "Build your profile once", body: "Four short steps: about you, your studies, your skills and your documents." },
  { icon: FolderLock, title: "Keep documents in your vault", body: "Transcripts, certificates and your CV, stored privately and scanned for viruses." },
  { icon: ShieldCheck, title: "Apply and stay in control", body: "Attach vault documents to any application and see which hiring teams opened them." },
];

function HowItWorks() {
  const { user } = useAuth();
  return (
    <section>
      <Container className="py-14">
        <h2 className="text-2xl font-semibold">Paperless applications</h2>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, body }) => (
            <Card key={title} className="p-5">
              <span className="grid size-10 place-items-center rounded-lg bg-brand-soft text-brand">
                <Icon className="size-5" aria-hidden />
              </span>
              <h3 className="mt-4 font-semibold">{title}</h3>
              <p className="mt-1 text-sm text-muted">{body}</p>
            </Card>
          ))}
        </div>
        <div className="mt-8">
          {user ? (
            <ButtonLink to="/profile">Go to your profile</ButtonLink>
          ) : (
            <ButtonLink to="/register">Create your free account</ButtonLink>
          )}
        </div>
      </Container>
    </section>
  );
}

function EmployerBand() {
  return (
    <section>
      <Container className="pb-4">
        <div className="flex flex-col items-start justify-between gap-6 rounded-2xl bg-brand p-8 text-on-brand sm:flex-row sm:items-center">
          <div>
            <h2 className="text-2xl font-semibold">Hiring students or graduates?</h2>
            <p className="mt-1 opacity-90">Post roles, collect applications with verified documents, and run campus recruitment drives.</p>
          </div>
          <Link to="/companies/join" className="inline-flex h-11 shrink-0 items-center gap-2 rounded-lg bg-surface px-5 text-sm font-medium text-text hover:bg-surface-2">
            Hire on SimplyFind <ArrowRight className="size-4" aria-hidden />
          </Link>
        </div>
      </Container>
    </section>
  );
}

export default function Home() {
  useTitle(null);
  return (
    <>
      <Hero />
      <LatestRoles />
      <Categories />
      <HowItWorks />
      <EmployerBand />
    </>
  );
}
