import { Link, useLocation } from "react-router-dom";
import { AlertTriangle, Briefcase, Plus, Users } from "lucide-react";
import { JOB_STATUS, companyApi } from "../../api/company";
import { errorMessage } from "../../api/client";
import { Alert, Badge, ButtonLink, Card, EmptyState, Spinner } from "../../components/ui";
import { ROLE_TYPES, deadlineInfo, formatDate } from "../../lib/format";
import { useApi, useTitle } from "../../lib/hooks";
import { useCompany } from "./CompanyLayout";

export default function CompanyJobs() {
  useTitle("Company jobs");
  const { company } = useCompany();
  const { data: jobs, loading, error } = useApi((signal) => companyApi.jobs({ signal }), []);
  const notice = useLocation().state?.notice; // set by the job form after saving

  const postButton = company.can_post && (
    <ButtonLink to="/company/jobs/new">
      <Plus className="size-4" /> Post a job
    </ButtonLink>
  );

  if (loading && !jobs) return <Spinner />;
  if (error) return <Alert tone="danger">{errorMessage(error)}</Alert>;

  return (
    <div>
      {notice && <Alert tone="success" className="mb-4">{notice}</Alert>}
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="text-xl font-semibold">Jobs</h2>
        {postButton}
      </div>
      {jobs.length === 0 ? (
        <EmptyState icon={Briefcase} title="No jobs yet" action={postButton}>
          {company.can_post ? "Post your first internship, graduate programme or entry-level role." : "You can post jobs once your company is approved."}
        </EmptyState>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => {
            const status = JOB_STATUS[job.status] || { label: job.status, tone: "neutral" };
            const deadline = deadlineInfo(job.application_deadline);
            const closed = job.status === "approved" && !job.is_open;
            return (
              <Card key={job.id} className="flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link to={`/company/jobs/${job.id}/edit`} className="truncate font-semibold hover:text-brand">{job.title}</Link>
                    <Badge tone={closed ? "neutral" : status.tone}>{closed ? "Closed" : status.label}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted">
                    {ROLE_TYPES[job.role_type]} · {job.location || "No location"} · {job.application_method === "in_app" ? "Apply on SimplyFind" : "Apply on your site"}
                    {deadline && ` · ${deadline.label}`} · Posted {formatDate(job.submitted_at)}
                  </p>
                  {job.status === "rejected" && job.rejection_reason && <p className="mt-2 text-sm text-danger">{job.rejection_reason}</p>}
                  {job.flagged_terms?.length > 0 && (
                    <p className="mt-2 inline-flex items-center gap-1 text-xs text-danger">
                      <AlertTriangle className="size-3.5" /> A question may ask about a protected characteristic ({job.flagged_terms.join(", ")}).
                    </p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {job.application_method === "in_app" && (
                    <ButtonLink to={`/company/jobs/${job.id}/applicants`} variant="secondary" size="sm">
                      <Users className="size-4" /> {job.application_count} applicant{job.application_count === 1 ? "" : "s"}
                    </ButtonLink>
                  )}
                  <ButtonLink to={`/company/jobs/${job.id}/edit`} variant="ghost" size="sm">Edit</ButtonLink>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
