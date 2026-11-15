import { Link, useParams } from "react-router-dom";
import { BadgeCheck, CalendarDays, MapPin } from "lucide-react";
import { drivesApi } from "../api/company";
import { errorMessage } from "../api/client";
import { Alert, Badge, ButtonLink, Card, Container, Spinner } from "../components/ui";
import { useAuth } from "../context/AuthContext";
import { ROLE_TYPES, WORK_MODES, deadlineInfo, formatDate } from "../lib/format";
import { useApi, useTitle } from "../lib/hooks";
import NotFound from "./NotFound";

/* /d/:code: what a drive's QR code opens. */
export default function PublicDrive() {
  const { code } = useParams();
  const { user } = useAuth();
  const { data: drive, loading, error } = useApi((signal) => drivesApi.publicDrive(code, { signal }), [code, user?.id]);
  useTitle(drive ? `${drive.name}, ${drive.company.name}` : "Recruitment drive");

  if (loading && !drive) return <Spinner />;
  if (error?.response?.status === 404) return <NotFound />;
  if (error) {
    return (
      <Container className="py-10">
        <Alert tone="danger">{errorMessage(error)}</Alert>
      </Container>
    );
  }

  return (
    <Container className="py-10">
      <div className="mx-auto max-w-2xl">
        <Card className="p-6 sm:p-8">
          <div className="flex items-center gap-3">
            {drive.company.logo_url ? (
              <img src={drive.company.logo_url} alt="" className="size-12 rounded-lg object-contain" />
            ) : (
              <span className="grid size-12 place-items-center rounded-lg bg-brand-soft text-xl font-bold text-brand">{drive.company.name.charAt(0)}</span>
            )}
            <Link to={`/companies/${drive.company.slug}`} className="flex items-center gap-1 font-medium hover:text-brand">
              {drive.company.name}
              {drive.company.is_verified && <BadgeCheck className="size-4 text-brand" aria-label="Verified company" />}
            </Link>
          </div>
          <h1 className="mt-5 text-3xl font-bold tracking-tight">{drive.name}</h1>
          <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-muted">
            {drive.location && <span className="inline-flex items-center gap-1"><MapPin className="size-4" /> {drive.location}</span>}
            {drive.starts_on && (
              <span className="inline-flex items-center gap-1">
                <CalendarDays className="size-4" /> {formatDate(drive.starts_on)}{drive.ends_on && drive.ends_on !== drive.starts_on ? ` to ${formatDate(drive.ends_on)}` : ""}
              </span>
            )}
          </div>
          {drive.description && <p className="mt-4 whitespace-pre-line">{drive.description}</p>}
          {!user && (
            <div className="mt-6 rounded-xl bg-brand-soft p-5">
              <p className="font-medium">Sign up to apply</p>
              <p className="mt-1 text-sm text-muted">Create a free account, add your documents once, and apply for {drive.company.name}'s roles in minutes.</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <ButtonLink to={`/register?drive=${drive.code}&next=${encodeURIComponent(`/d/${drive.code}`)}`}>Create my account</ButtonLink>
                <ButtonLink to={`/login?next=${encodeURIComponent(`/d/${drive.code}`)}`} variant="secondary">I have an account</ButtonLink>
              </div>
            </div>
          )}
        </Card>

        <h2 className="mt-8 mb-4 text-xl font-semibold">Open roles</h2>
        {drive.jobs.length === 0 ? (
          <p className="text-sm text-muted">No roles are open right now.</p>
        ) : (
          <div className="space-y-3">
            {drive.jobs.map((j) => {
              const deadline = deadlineInfo(j.application_deadline);
              return (
                <Link key={j.id} to={`/opportunities/${j.id}`} className="block">
                  <Card className="p-4 transition-colors hover:border-brand">
                    <p className="font-semibold">{j.title}</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                      <Badge tone="brand">{ROLE_TYPES[j.role_type]}</Badge>
                      {j.work_mode && <Badge>{WORK_MODES[j.work_mode]}</Badge>}
                      {j.application_method === "in_app" && <Badge tone="accent">Apply on SimplyFind</Badge>}
                      {deadline && <span>{deadline.label}</span>}
                    </div>
                  </Card>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </Container>
  );
}
