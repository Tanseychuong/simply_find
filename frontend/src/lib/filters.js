/*
  The role list's filters. Each `key` is the API's own query parameter
  (backend/apps/opportunities/services.py: filter_by_role), so the page URL
  and the API request use the same names.

  kind: "multi"  comma-separated list, matches any value
        "single" one value or none
        "toggle" "true" or absent
*/
import { ROLE_TYPES, WORK_MODES } from "./format";

export const EMPLOYMENT_TYPES = { full_time: "Full-time", part_time: "Part-time" };

export const CAREER_LEVELS = {
  no_experience: "No experience needed",
  some_experience: "Up to 1 year of experience",
  early_career: "Up to 2 years of experience",
};

export const DEADLINES = { week: "Closing within a week", month: "Closing within a month", rolling: "No deadline (rolling)" };

export const POSTED = { 1: "Last 24 hours", 7: "Last 7 days", 30: "Last 30 days" };

export const DURATIONS = { short: "Up to 3 months", medium: "4 to 6 months", long: "7 months or more" };

export const TOGGLES = {
  paid: "Paid roles only",
  apply_on_site: "Apply on SimplyFind",
  verified: "Verified companies",
  open_to_minors: "Open to under-18s",
};

export const FILTERS = [
  { key: "role_type", kind: "multi", label: "Type of role", options: ROLE_TYPES },
  { key: "career_level", kind: "multi", label: "Career level", options: CAREER_LEVELS },
  { key: "category", kind: "multi", label: "Industry" }, // options come from /categories/
  { key: "location", kind: "multi", label: "Location" }, // options come from /locations/
  { key: "work_mode", kind: "multi", label: "Where you work", options: WORK_MODES },
  { key: "employment_type", kind: "multi", label: "Hours", options: EMPLOYMENT_TYPES },
  { key: "deadline", kind: "single", label: "Deadline", options: DEADLINES },
  { key: "posted_within", kind: "single", label: "Date posted", options: POSTED },
  { key: "duration", kind: "multi", label: "Internship length", options: DURATIONS },
  ...Object.entries(TOGGLES).map(([key, label]) => ({ key, kind: "toggle", label })),
  { key: "graduation_year", kind: "single", label: "Graduation year" },
];

export const FILTER_KEYS = FILTERS.map((f) => f.key);

/** One removable chip per active value: [{key, value, label}]. */
export function activeChips(params, { categories = [] } = {}) {
  const chips = [];
  for (const f of FILTERS) {
    const raw = params.get(f.key);
    if (!raw) continue;
    if (f.kind === "toggle") {
      if (raw === "true") chips.push({ key: f.key, value: raw, label: f.label });
    } else if (f.key === "graduation_year") {
      chips.push({ key: f.key, value: raw, label: `Graduates of ${raw}` });
    } else {
      const values = f.kind === "multi" ? raw.split(",").filter(Boolean) : [raw];
      for (const value of values) {
        let label = f.options?.[value];
        if (f.key === "category") label = categories.find((c) => c.slug === value)?.name;
        if (f.key === "location") label = value;
        if (label) chips.push({ key: f.key, value, label });
      }
    }
  }
  return chips;
}
