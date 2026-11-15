import { Suspense } from "react";
import { NavLink, Outlet, useOutletContext } from "react-router-dom";
import { BadgeCheck, Briefcase, Building2, QrCode, Users } from "lucide-react";
import { companyApi } from "../../api/company";
import { errorCodeOf, errorMessage } from "../../api/client";
import { Alert, Container, Spinner, cx } from "../../components/ui";
import { useApi } from "../../lib/hooks";

/*
  /company: the hiring team's dashboard. Every request here needs a session
  that passed two-step sign-in; when it hasn't, the API client sends the
  person to set it up or to sign in again (AuthContext's mfa handler).
*/
export function useCompany() {
  return useOutletContext();
}

const tab = ({ isActive }) =>
  cx(
    "flex items-center gap-2 border-b-2 px-1 pb-3 text-sm font-medium whitespace-nowrap transition-colors",
    isActive ? "border-brand text-brand" : "border-transparent text-muted hover:text-text",
  );

function StatusBanner({ company }) {
  if (company.status === "pending") {
    return (
      <Alert tone="warning" className="mb-6">
        <strong>We're reviewing your company.</strong> You can set up your profile and team now; jobs can be posted once you're approved
        (usually within two working days).
      </Alert>
    );
  }
  if (company.status === "rejected") {
    return (
      <Alert tone="danger" className="mb-6">
        <strong>Your company wasn't approved.</strong> {company.rejection_reason} Update your company profile to send it for review again.
      </Alert>
    );
  }
  if (company.status === "suspended") {
    return (
      <Alert tone="danger" className="mb-6">
        <strong>Your company account is suspended.</strong> {company.rejection_reason} Your jobs are hidden and applications are unavailable.
      </Alert>
    );
  }
  if (!company.is_verified) {
    return (
      <Alert tone="info" className="mb-6">
        Your jobs are checked by our team before they go live. Verified companies publish straight away.
      </Alert>
    );
  }
  return null;
}

export default function CompanyLayout() {
  const { data: company, loading, error, setData: setCompany } = useApi((signal) => companyApi.me({ signal }), []);

  if (loading && !company) return <Spinner />;
  if (error) {
    // mfa_* codes are redirected by the API client; show nothing in between.
    if (/^mfa_/.test(errorCodeOf(error) || "")) return <Spinner label="Checking two-step sign-in" />;
    return (
      <Container className="py-8 sm:py-10">
        <Alert tone="danger">{errorMessage(error)}</Alert>
      </Container>
    );
  }

  return (
    <Container className="py-6 sm:py-8">
      <header className="mb-6 flex items-center gap-4">
        {company.logo_url ? (
          <img src={company.logo_url} alt="" className="size-14 rounded-xl border border-border bg-surface object-contain p-1" />
        ) : (
          <span className="grid size-14 place-items-center rounded-xl bg-brand-soft text-2xl font-bold text-brand">{company.name.charAt(0)}</span>
        )}
        <div className="min-w-0">
          <h1 className="flex items-center gap-2 truncate text-2xl font-bold tracking-tight">
            {company.name}
            {company.is_verified && <BadgeCheck className="size-5 shrink-0 text-brand" aria-label="Verified company" />}
          </h1>
          <p className="text-sm text-muted">Company dashboard · you're {company.my_role === "owner" ? "an owner" : `a ${company.my_role}`}</p>
        </div>
      </header>
      <StatusBanner company={company} />
      <nav aria-label="Company" className="mb-8 flex gap-6 overflow-x-auto border-b border-border">
        <NavLink to="/company" end className={tab}><Briefcase className="size-4" /> Jobs</NavLink>
        <NavLink to="/company/drives" className={tab}><QrCode className="size-4" /> Recruitment drives</NavLink>
        <NavLink to="/company/team" className={tab}><Users className="size-4" /> Team</NavLink>
        <NavLink to="/company/profile" className={tab}><Building2 className="size-4" /> Company profile</NavLink>
      </nav>
      <Suspense fallback={<Spinner />}>
        <Outlet context={{ company, setCompany }} />
      </Suspense>
    </Container>
  );
}
