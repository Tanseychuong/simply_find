import { Link, useLocation, useParams } from "react-router-dom";
import {
  ArrowLeft, BadgeCheck, Briefcase, CalendarClock, CheckCircle2, Clock, ExternalLink, GraduationCap,
  MapPin, Monitor, Wallet,
} from "lucide-react";
import { opportunitiesApi } from "../api/opportunities";
import { errorMessage } from "../api/client";
import CoverImage from "../components/opportunities/CoverImage";
import { RoleBadges } from "../components/opportunities/OpportunityCard";
import SaveButton from "../components/opportunities/SaveButton";
import Sections from "../components/opportunities/Sections";
import { Alert, ButtonLink, Card, Container, Spinner, buttonClass, cx } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import {
  ROLE_TYPES, WORK_MODES, deadlineInfo, experienceLabel, formatDate, graduationRange, organisationOf, timeAgo,
} from "../lib/format";
import { useApi, useTitle } from "../lib/hooks";
import { hostOf, safeExternalUrl } from "../lib/urls";
import NotFound from "./NotFound";

function ApplyPanel({ opp }) {
  const { user } = useAuth();
  const location = useLocation();
  const deadline = deadlineInfo(opp.application_deadline);
  const closed = opp.is_open === false || deadline?.closed;

  if (opp.has_applied) {
    return (
      <div className="space-y-3">
        <Alert tone="success">
          <span className="inline-flex items-center gap-2 font-medium">
            <CheckCircle2 className="size-4" /> You applied for this role
          </span>
        </Alert>
        <ButtonLink to="/applications" variant="secondary" className="w-full">Track your application</ButtonLink>
      </div>
    );
  }
  if (closed) {
    return <Alert tone="warning">Applications for this role have closed.</Alert>;
  }

  if (opp.application_method === "in_app") {
    if (!user) {
      const next = encodeURIComponent(location.pathname);
      return (
        <div className="space-y-2">
          <ButtonLink to={`/login?next=${next}`} size="lg" className="w-full">Sign in to apply</ButtonLink>
          <p className="text-center text-xs text-muted">
            New here? <Link to={`/register?next=${next}`} className="font-medium text-brand hover:underline">Create a free account</Link>
          </p>
        </div>
      );
    }
    return (
      <div className="space-y-2">
        <ButtonLink to={`/opportunities/${opp.id}/apply`} size="lg" className="w-full">Apply with your profile</ButtonLink>
        <p className="text-center text-xs text-muted">Attach documents from your vault. No uploads needed twice.</p>
      </div>
    );
  }

  const url = safeExternalUrl(opp.opportunity_url);
  if (!url) return <p className="text-sm text-muted">See "How to apply" in the description.</p>;
  return (
    <div className="space-y-2">
      <a href={url} target="_blank" rel="noopener noreferrer nofollow" className={buttonClass({ size: "lg", className: "w-full" })}>
        Apply on {hostOf(url) || "the organiser's site"} <ExternalLink className="size-4" aria-hidden />
      </a>
      <p className="text-center text-xs text-muted">You'll apply on the organiser's own website.</p>
    </div>
  );
}

function Fact({ icon: Icon, label, children }) {
  if (!children) return null;
  return (
    <div className="flex gap-3">
      <Icon className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />
      <div>
        <dt className="text-xs text-muted">{label}</dt>
        <dd className="text-sm font-medium">{children}</dd>
      </div>
    </div>
  );
}

function Facts({ opp }) {
  const deadline = deadlineInfo(opp.application_deadline);
  const paid = opp.is_paid === true ? "Paid" : opp.is_paid === false ? "Unpaid" : null;
  return (
    <dl className="space-y-4">
      <Fact icon={Briefcase} label="Type">
        {ROLE_TYPES[opp.role_type]}
        {opp.duration_months ? `, ${opp.duration_months} month${opp.duration_months === 1 ? "" : "s"}` : ""}
      </Fact>
      <Fact icon={MapPin} label="Location">{opp.location}</Fact>
      <Fact icon={Monitor} label="Work mode">{WORK_MODES[opp.work_mode]}</Fact>
      <Fact icon={Wallet} label="Pay">{paid}</Fact>
      <Fact icon={GraduationCap} label="Who can apply">
        {[graduationRange(opp.graduation_year_min, opp.graduation_year_max), experienceLabel(opp.experience_years_max), opp.accepts_minors ? "Open to under-18s" : null]
          .filter(Boolean)
          .join(". ") || null}
      </Fact>
      <Fact icon={CalendarClock} label="Deadline">
        {deadline && (
          <span className={cx(deadline.urgent && "text-danger")}>
            {formatDate(opp.application_deadline, { day: "numeric", month: "long", year: "numeric" })}
            {deadline.urgent ? ` (${deadline.label.toLowerCase()})` : ""}
          </span>
        )}
      </Fact>
      <Fact icon={Clock} label="Posted">{timeAgo(opp.published_at)}</Fact>
    </dl>
  );
}

export default function OpportunityDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  // Reload when the visitor signs in or out: has_applied and is_saved depend on it.
  const { data: opp, loading, error } = useApi((signal) => opportunitiesApi.get(id, { signal }), [id, user?.id]);
  useTitle(opp ? `${opp.title}, ${organisationOf(opp)}` : null);

  if (loading && !opp) return <Spinner />;
  if (error?.response?.status === 404) return <NotFound />;
  if (error) {
    return (
      <Container className="py-10">
        <Alert tone="danger">{errorMessage(error)}</Alert>
      </Container>
    );
  }

  const org = organisationOf(opp);
  return (
    <Container className="py-8">
      <Link to="/opportunities" className="mb-6 inline-flex items-center gap-1 text-sm text-muted hover:text-text">
        <ArrowLeft className="size-4" /> All roles
      </Link>

      <div className="grid gap-8 lg:grid-cols-[1fr_320px]">
        <article className="min-w-0">
          {/* No placeholder here: a big empty banner adds nothing to a page that has a title. */}
          {safeExternalUrl(opp.image_url) && (
            <CoverImage src={opp.image_url} roleType={opp.role_type} organisation={org} className="mb-6 aspect-[21/9] w-full rounded-xl" />
          )}
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="flex items-center gap-1.5 text-sm font-medium text-muted">
                {opp.company ? (
                  <Link to={`/companies/${opp.company.slug}`} className="hover:text-brand">{org}</Link>
                ) : (
                  org
                )}
                {opp.company?.is_verified && <BadgeCheck className="size-4 text-brand" aria-label="Verified company" />}
              </p>
              <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-3xl">{opp.title}</h1>
            </div>
            <SaveButton key={`${opp.id}-${opp.is_saved}`} opportunity={opp} withLabel className="shrink-0 border border-border" />
          </div>
          <div className="mt-4">
            <RoleBadges opp={opp} />
          </div>

          {/* On small screens the apply box comes before the long description. */}
          <Card className="mt-6 p-5 lg:hidden">
            <ApplyPanel opp={opp} />
          </Card>

          <div className="mt-8">
            <Sections sections={opp.sections} description={opp.description} />
          </div>
        </article>

        <aside className="space-y-4 lg:sticky lg:top-24 lg:self-start">
          <Card className="hidden p-5 lg:block">
            <ApplyPanel opp={opp} />
          </Card>
          <Card className="p-5">
            <Facts opp={opp} />
          </Card>
          {opp.company && (
            <Card className="flex items-center gap-3 p-4">
              {opp.company.logo_url ? (
                <img src={opp.company.logo_url} alt="" className="size-10 rounded-lg object-contain" />
              ) : (
                <span className="grid size-10 place-items-center rounded-lg bg-brand-soft font-semibold text-brand">{org.charAt(0)}</span>
              )}
              <div className="min-w-0">
                <p className="truncate text-sm font-medium">{org}</p>
                <Link to={`/companies/${opp.company.slug}`} className="text-xs text-brand hover:underline">See all their roles</Link>
              </div>
            </Card>
          )}
        </aside>
      </div>
    </Container>
  );
}
