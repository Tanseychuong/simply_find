import { Link } from "react-router-dom";
import { ArrowRight, CheckCircle2, Circle, PartyPopper } from "lucide-react";
import { ButtonLink, Card } from "../../components/ui";
import { useTitle } from "../../lib/hooks";
import { STEP_PATHS, useProfile } from "./ProfileLayout";

export default function ProfileOverview() {
  useTitle("My profile");
  const { profile } = useProfile();
  const { steps, next_step: next } = profile.progress;
  const readyToApply = steps.filter((s) => s.key === "about" || s.key === "studies").every((s) => s.done);

  return (
    <div className="space-y-6">
      {next ? (
        <Card className="flex flex-col items-start gap-4 border-brand/30 bg-brand-soft/40 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-semibold">{readyToApply ? "You can apply for roles now" : "Finish the first two steps to apply"}</p>
            <p className="mt-1 text-sm text-muted">
              Next: {steps.find((s) => s.key === next).label.toLowerCase()}.
              {readyToApply ? " A complete profile helps hiring teams pick you." : " Applying needs your details and your studies."}
            </p>
          </div>
          <ButtonLink to={`/profile/${STEP_PATHS[next]}`}>
            Continue <ArrowRight className="size-4" />
          </ButtonLink>
        </Card>
      ) : (
        <Card className="flex items-center gap-3 border-success/30 bg-success-soft p-5">
          <PartyPopper className="size-6 text-success" aria-hidden />
          <div>
            <p className="font-semibold">Your profile is complete</p>
            <p className="text-sm text-muted">
              <Link to="/opportunities" className="font-medium text-brand hover:underline">Find a role</Link> and apply with your documents.
            </p>
          </div>
        </Card>
      )}

      <ol className="space-y-3">
        {steps.map((s, i) => (
          <li key={s.key}>
            <Link to={`/profile/${STEP_PATHS[s.key]}`} className="block rounded-xl border border-border bg-surface p-4 transition-colors hover:border-brand">
              <div className="flex items-start gap-3">
                {s.done ? <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-success" /> : <Circle className="mt-0.5 size-5 shrink-0 text-muted" />}
                <div className="flex-1">
                  <p className="font-medium">
                    <span className="text-muted">Step {i + 1}.</span> {s.label}
                  </p>
                  {s.done ? (
                    <p className="mt-0.5 text-sm text-muted">Done</p>
                  ) : (
                    <p className="mt-0.5 text-sm text-muted">Still needed: {s.missing.map((m) => m.label).join(", ")}</p>
                  )}
                </div>
                <ArrowRight className="mt-0.5 size-4 text-muted" aria-hidden />
              </div>
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}
