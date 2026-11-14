import { Link } from "react-router-dom";
import { BadgeCheck, Clock, MapPin } from "lucide-react";
import { ROLE_TYPES, WORK_MODES, deadlineInfo, organisationOf } from "../../lib/format";
import { EMPLOYMENT_TYPES } from "../../lib/filters";
import { Badge, cx } from "../ui";
import CoverImage from "./CoverImage";
import SaveButton from "./SaveButton";

export function RoleBadges({ opp }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {opp.role_type && <Badge tone="brand">{ROLE_TYPES[opp.role_type] || opp.role_type}</Badge>}
      {opp.work_mode && <Badge>{WORK_MODES[opp.work_mode]}</Badge>}
      {opp.employment_type && <Badge>{EMPLOYMENT_TYPES[opp.employment_type]}</Badge>}
      {opp.is_paid === true && <Badge tone="success">Paid</Badge>}
      {opp.is_paid === false && <Badge>Unpaid</Badge>}
      {opp.application_method === "in_app" && <Badge tone="accent">Apply on SimplyFind</Badge>}
    </div>
  );
}

export default function OpportunityCard({ opp, layout = "grid" }) {
  const deadline = deadlineInfo(opp.application_deadline);
  const org = organisationOf(opp);

  return (
    <article
      className={cx(
        "group relative flex overflow-hidden rounded-xl border border-border bg-surface transition-shadow hover:shadow-md",
        layout === "grid" ? "flex-col" : "flex-col sm:flex-row",
      )}
    >
      <CoverImage
        src={opp.image_url}
        roleType={opp.role_type}
        organisation={org}
        className={layout === "grid" ? "aspect-[3/1] w-full sm:aspect-[16/9]" : "aspect-[3/1] w-full sm:aspect-auto sm:w-56 sm:shrink-0"}
      />
      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="flex items-center gap-1 truncate text-xs font-medium text-muted">
              {org}
              {opp.company?.is_verified && <BadgeCheck className="size-3.5 shrink-0 text-brand" aria-label="Verified company" />}
            </p>
            <h3 className="mt-1 line-clamp-2 font-semibold leading-snug">
              {/* The whole card is clickable through this link's ::after. */}
              <Link to={`/opportunities/${opp.id}`} className="after:absolute after:inset-0 group-hover:text-brand">
                {opp.title}
              </Link>
            </h3>
          </div>
          <SaveButton opportunity={opp} className="relative z-10 -mt-1 -mr-1 shrink-0" />
        </div>
        <RoleBadges opp={opp} />
        <div className="mt-auto flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
          {opp.location && (
            <span className="inline-flex items-center gap-1">
              <MapPin className="size-3.5" aria-hidden /> {opp.location}
            </span>
          )}
          {deadline && (
            <span className={cx("inline-flex items-center gap-1", deadline.urgent && "font-medium text-danger")}>
              <Clock className="size-3.5" aria-hidden /> {deadline.label}
            </span>
          )}
        </div>
      </div>
    </article>
  );
}

export function CardSkeleton() {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface" aria-hidden>
      <div className="aspect-[3/1] animate-pulse bg-surface-2 sm:aspect-[16/9]" />
      <div className="space-y-3 p-4">
        <div className="h-3 w-1/3 animate-pulse rounded bg-surface-2" />
        <div className="h-4 w-4/5 animate-pulse rounded bg-surface-2" />
        <div className="h-5 w-1/2 animate-pulse rounded bg-surface-2" />
      </div>
    </div>
  );
}
