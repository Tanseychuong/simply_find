import { useState } from "react";
import { Link } from "react-router-dom";
import { BadgeCheck, Clock, ExternalLink, MapPin, Zap } from "lucide-react";
import { ROLE_TYPES, WORK_MODES, deadlineInfo, organisationOf, timeAgo } from "../../lib/format";
import { EMPLOYMENT_TYPES } from "../../lib/filters";
import { Badge, cx } from "../ui";
import SaveButton from "./SaveButton";

/** Used on the role page; the card itself shows fewer, quieter tags. */
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

/* Soft tile colours for organisations without a logo, picked from the name so
   the same organisation always gets the same colour. */
const TILES = [
  "bg-teal-100 text-teal-800 dark:bg-teal-400/15 dark:text-teal-300",
  "bg-sky-100 text-sky-800 dark:bg-sky-400/15 dark:text-sky-300",
  "bg-indigo-100 text-indigo-800 dark:bg-indigo-400/15 dark:text-indigo-300",
  "bg-amber-100 text-amber-800 dark:bg-amber-400/15 dark:text-amber-300",
  "bg-rose-100 text-rose-800 dark:bg-rose-400/15 dark:text-rose-300",
  "bg-emerald-100 text-emerald-800 dark:bg-emerald-400/15 dark:text-emerald-300",
];

function initials(name) {
  const words = (name || "").replace(/[^\p{L}\p{N}\s]/gu, "").split(/\s+/).filter(Boolean);
  return ((words[0]?.[0] || "") + (words[1]?.[0] || "")).toUpperCase() || "?";
}

export function OrgLogo({ name, src, className }) {
  const [failed, setFailed] = useState(false);
  const size = cx("size-11 shrink-0 rounded-lg", className);
  if (src && !failed) {
    return (
      <img src={src} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)}
        className={cx(size, "border border-border bg-white object-contain p-1")} />
    );
  }
  let hash = 0;
  for (const ch of name || "") hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return (
    <div aria-hidden className={cx(size, "flex items-center justify-center text-sm font-semibold", TILES[hash % TILES.length])}>
      {initials(name)}
    </div>
  );
}

export default function OpportunityCard({ opp }) {
  const deadline = deadlineInfo(opp.application_deadline);
  const org = organisationOf(opp);
  // "Remote · Remote" when the location already says it.
  const mode = opp.work_mode && WORK_MODES[opp.work_mode];
  const facts = [
    mode && !(opp.location || "").toLowerCase().includes(mode.toLowerCase()) && mode,
    opp.employment_type && EMPLOYMENT_TYPES[opp.employment_type],
  ].filter(Boolean);
  const inApp = opp.application_method === "in_app";

  const deadlineEl = deadline ? (
    <span className={cx("inline-flex items-center gap-1", deadline.urgent ? "font-medium text-danger" : "text-muted")}>
      <Clock className="size-3.5" aria-hidden /> {deadline.label}
    </span>
  ) : (
    <span className="text-muted">No fixed deadline</span>
  );
  const applyEl = inApp ? (
    <span className="inline-flex items-center gap-1 font-medium text-brand">
      <Zap className="size-3.5" aria-hidden /> Easy apply
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-muted">
      <ExternalLink className="size-3.5" aria-hidden /> Organiser's site
    </span>
  );

  // A wide row: logo | title, organisation, details, tags | deadline and how to apply | save.
  return (
    <article className="group relative flex items-start gap-4 rounded-xl border border-border bg-surface p-4 transition hover:border-brand/40 hover:shadow-md sm:items-center sm:px-5">
      <OrgLogo name={org} src={opp.company?.logo_url} className="sm:size-12" />

      <div className="min-w-0 flex-1">
        <h3 className="line-clamp-2 text-base font-semibold leading-snug sm:line-clamp-1">
          {/* The whole card is clickable through this link's ::after. */}
          <Link to={`/opportunities/${opp.id}`} className="after:absolute after:inset-0 after:rounded-xl group-hover:text-brand">
            {opp.title}
          </Link>
        </h3>
        <p className="mt-0.5 flex items-center gap-1 text-sm">
          <span className="truncate font-medium">{org}</span>
          {opp.company?.is_verified && <BadgeCheck className="size-4 shrink-0 text-brand" aria-label="Verified company" />}
          {opp.category?.name && <span className="hidden truncate text-muted md:inline">· {opp.category.name}</span>}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-sm text-muted">
          {(opp.location || facts.length > 0) && (
            <span className="inline-flex max-w-full min-w-0 items-center gap-1">
              {opp.location && <MapPin className="size-3.5 shrink-0" aria-hidden />}
              <span className="truncate">{[opp.location, ...facts].filter(Boolean).join(" · ")}</span>
            </span>
          )}
          <span className="flex flex-wrap gap-1.5">
            {opp.role_type && <Badge tone="brand">{ROLE_TYPES[opp.role_type] || opp.role_type}</Badge>}
            {opp.is_paid === true && <Badge tone="success">Paid</Badge>}
            {opp.is_paid === false && <Badge>Unpaid</Badge>}
          </span>
        </div>
        {/* On phones the deadline and how to apply go under the details. */}
        <div className="mt-3 flex items-center justify-between gap-3 text-xs whitespace-nowrap sm:hidden">
          {deadlineEl}
          {applyEl}
        </div>
      </div>

      <div className="hidden shrink-0 flex-col items-end gap-1.5 border-l border-border pl-5 text-xs whitespace-nowrap sm:flex sm:min-w-40">
        {deadlineEl}
        {applyEl}
        <span className="text-muted">{timeAgo(opp.published_at)}</span>
      </div>

      <SaveButton opportunity={opp} className="relative z-10 -mt-1.5 -mr-2 shrink-0 sm:mt-0" />
    </article>
  );
}

export function CardSkeleton() {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-border bg-surface p-4 sm:px-5" aria-hidden>
      <div className="size-11 shrink-0 animate-pulse rounded-lg bg-surface-2 sm:size-12" />
      <div className="flex-1 space-y-2">
        <div className="h-4 w-1/2 animate-pulse rounded bg-surface-2" />
        <div className="h-3 w-1/3 animate-pulse rounded bg-surface-2" />
        <div className="h-5 w-2/3 animate-pulse rounded bg-surface-2" />
      </div>
      <div className="hidden w-32 space-y-2 sm:block">
        <div className="h-3 animate-pulse rounded bg-surface-2" />
        <div className="h-3 animate-pulse rounded bg-surface-2" />
      </div>
    </div>
  );
}
