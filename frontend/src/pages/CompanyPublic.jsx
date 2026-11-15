import { useParams } from "react-router-dom";
import { BadgeCheck, Briefcase, ExternalLink, MapPin, Users } from "lucide-react";
import { companiesApi } from "../api/companies";
import { errorMessage } from "../api/client";
import OpportunityCard from "../components/opportunities/OpportunityCard";
import { Alert, Container, EmptyState, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { useApi, useTitle } from "../lib/hooks";
import { hostOf, safeExternalUrl } from "../lib/urls";
import NotFound from "./NotFound";

export default function CompanyPublic() {
  const { slug } = useParams();
  const { user } = useAuth();
  const { data, loading, error } = useApi((signal) => companiesApi.publicProfile(slug, { signal }), [slug, user?.id]);
  useTitle(data?.company?.name);

  if (loading && !data) return <Spinner />;
  if (error?.response?.status === 404) return <NotFound />;
  if (error) {
    return (
      <Container className="py-10">
        <Alert tone="danger">{errorMessage(error)}</Alert>
      </Container>
    );
  }

  const { company, jobs } = data;
  const website = safeExternalUrl(company.website);
  return (
    <>
      <section className="border-b border-border bg-surface">
        <Container className="flex flex-col gap-6 py-10 sm:flex-row sm:items-center">
          {company.logo_url ? (
            <img src={company.logo_url} alt="" className="size-20 rounded-xl border border-border bg-surface object-contain p-2" />
          ) : (
            <span className="grid size-20 place-items-center rounded-xl bg-brand-soft text-3xl font-bold text-brand">{company.name.charAt(0)}</span>
          )}
          <div className="min-w-0">
            <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
              {company.name}
              {company.is_verified && <BadgeCheck className="size-6 text-brand" aria-label="Verified company" />}
            </h1>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
              {company.industry && <span className="inline-flex items-center gap-1"><Briefcase className="size-4" /> {company.industry}</span>}
              {company.location && <span className="inline-flex items-center gap-1"><MapPin className="size-4" /> {company.location}</span>}
              {company.size && <span className="inline-flex items-center gap-1"><Users className="size-4" /> {company.size} people</span>}
              {website && (
                <a href={website} target="_blank" rel="noopener noreferrer nofollow" className="inline-flex items-center gap-1 text-brand hover:underline">
                  {hostOf(website)} <ExternalLink className="size-3.5" />
                </a>
              )}
            </div>
          </div>
        </Container>
      </section>
      <Container className="py-10">
        {company.description && <p className="mb-10 max-w-3xl leading-relaxed whitespace-pre-line text-muted">{company.description}</p>}
        <h2 className="mb-4 text-xl font-semibold">Open roles ({jobs.length})</h2>
        {jobs.length ? (
          <div className="grid grid-cols-1 gap-3">
            {jobs.map((o) => <OpportunityCard key={o.id} opp={o} />)}
          </div>
        ) : (
          <EmptyState icon={Briefcase} title="No open roles right now">Check back soon.</EmptyState>
        )}
      </Container>
    </>
  );
}
