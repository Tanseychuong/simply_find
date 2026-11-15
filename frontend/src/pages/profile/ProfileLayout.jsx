import { Suspense } from "react";
import { NavLink, Outlet, useOutletContext } from "react-router-dom";
import { CheckCircle2, Circle } from "lucide-react";
import { profileApi } from "../../api/profile";
import { errorMessage } from "../../api/client";
import { Alert, Container, Spinner, cx } from "../../components/ui";
import { useApi } from "../../lib/hooks";

/*
  /profile and its steps. The profile (with `progress` from the API) is
  loaded once here and shared with each step through the outlet context.
*/
export const STEP_PATHS = { about: "about", studies: "studies", skills: "skills", documents: "documents" };

export function useProfile() {
  return useOutletContext();
}

export function ProgressBar({ value }) {
  return (
    <div className="h-2 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100} aria-label="Profile complete">
      <div className="h-full rounded-full bg-brand transition-all" style={{ width: `${value}%` }} />
    </div>
  );
}

const tab = ({ isActive }) =>
  cx(
    "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors",
    isActive ? "bg-brand-soft text-brand-strong" : "text-muted hover:bg-surface-2 hover:text-text",
  );

export default function ProfileLayout() {
  const { data: profile, error, loading, setData: setProfile, reload } = useApi((signal) => profileApi.get({ signal }), []);

  if (loading && !profile) return <Spinner />;
  if (error) {
    return (
      <Container className="py-10">
        <Alert tone="danger">{errorMessage(error)}</Alert>
      </Container>
    );
  }

  const { steps, completeness } = profile.progress;
  return (
    <Container className="py-8">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">My profile</h1>
          <p className="mt-1 text-sm text-muted">Hiring teams see your studies and skills. Your date of birth is never shown to them.</p>
        </div>
        <div className="w-full sm:w-64">
          <p className="mb-1.5 text-sm font-medium">{completeness}% complete</p>
          <ProgressBar value={completeness} />
        </div>
      </div>
      <div className="grid gap-8 lg:grid-cols-[220px_1fr]">
        <nav aria-label="Profile sections" className="-mx-4 flex gap-1 overflow-x-auto px-4 lg:mx-0 lg:flex-col lg:overflow-visible lg:px-0">
          <NavLink to="/profile" end className={tab}>Overview</NavLink>
          {steps.map((s) => (
            <NavLink key={s.key} to={`/profile/${STEP_PATHS[s.key]}`} className={tab}>
              {s.done ? <CheckCircle2 className="size-4 text-success" aria-label="Done" /> : <Circle className="size-4" aria-label="To do" />}
              {s.label}
            </NavLink>
          ))}
          <NavLink to="/profile/access" className={tab}>Who opened my files</NavLink>
        </nav>
        <div className="min-w-0">
          <Suspense fallback={<Spinner />}>
            <Outlet context={{ profile, setProfile, reloadProfile: reload }} />
          </Suspense>
        </div>
      </div>
    </Container>
  );
}
