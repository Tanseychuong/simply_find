/* Labels and formatting shared by listing cards, filters and detail pages. */

export const ROLE_TYPES = {
  internship: "Internship",
  graduate_programme: "Graduate programme",
  entry_level: "Entry-level role",
  graduate_school: "Graduate school",
};

export const WORK_MODES = { on_site: "On site", hybrid: "Hybrid", remote: "Remote" };

const DAY = 24 * 60 * 60 * 1000;

export function formatDate(value, opts = { day: "numeric", month: "short", year: "numeric" }) {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, opts);
}

/**
 * Deadline as people read it: "Closes today", "Closes in 3 days",
 * "Closes 20 Nov 2026", "Closed". `urgent` is true for the last 7 days.
 */
export function deadlineInfo(deadline, now = Date.now()) {
  if (!deadline) return null;
  const end = new Date(deadline).getTime();
  if (Number.isNaN(end)) return null;
  if (end < now) return { label: "Closed", closed: true, urgent: false };
  // Calendar days in the visitor's time zone, so "Closes tomorrow" means tomorrow's date.
  const startOfDay = (t) => {
    const d = new Date(t);
    d.setHours(0, 0, 0, 0);
    return d.getTime();
  };
  const days = Math.round((startOfDay(end) - startOfDay(now)) / DAY);
  if (days === 0) return { label: "Closes today", closed: false, urgent: true };
  if (days === 1) return { label: "Closes tomorrow", closed: false, urgent: true };
  if (days < 7) return { label: `Closes in ${days} days`, closed: false, urgent: true };
  return { label: `Closes ${formatDate(deadline)}`, closed: false, urgent: false };
}

export function timeAgo(value, now = Date.now()) {
  if (!value) return "";
  const diff = now - new Date(value).getTime();
  const days = Math.floor(diff / DAY);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 30) return `${days} days ago`;
  return formatDate(value);
}

/** "Graduates 2024–2026", "Graduates from 2025", or null. */
export function graduationRange(min, max) {
  if (min && max) return min === max ? `Graduates of ${min}` : `Graduates ${min}–${max}`;
  if (min) return `Graduates from ${min}`;
  if (max) return `Graduates up to ${max}`;
  return null;
}

export function experienceLabel(years) {
  if (years === null || years === undefined) return null;
  if (years === 0) return "No experience needed";
  return `Up to ${years} year${years === 1 ? "" : "s"} of experience`;
}

export function organisationOf(opp) {
  return opp.company?.name || opp.organization || "";
}

export function compactNumber(n) {
  if (n === null || n === undefined) return "–";
  return new Intl.NumberFormat(undefined, { notation: n >= 10000 ? "compact" : "standard" }).format(n);
}
