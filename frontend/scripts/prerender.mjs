/*
  Pre-render the public pages after `vite build`, so search engines and
  link previews (WhatsApp, LinkedIn...) see real content without running JS.

    node scripts/prerender.mjs        (npm run prerender)

  Environment:
    SITE_URL            the public website, e.g. https://simplyfind.example
                        (canonical links, og:url). Required for absolute URLs.
    PRERENDER_API_URL   where to read the data, e.g. https://simplyfind-api.onrender.com
                        Unset: only the static pages are written, and the build
                        still succeeds (the site works as a plain single-page app).

  Writes into dist/:
    app.html                         the untouched app shell; the host rewrites
                                     every path without its own file to it
    index.html                       home page
    opportunities/index.html         role list
    opportunities/<id>/index.html    each open role (JobPosting structured data)
    companies/<slug>/index.html      each approved company with open roles
    companies/join/index.html        employer page
    robots.txt                       with the sitemap (served by the API)

  React replaces the content inside #root when it starts, so these pages
  never go stale for a visitor; they only matter to crawlers. The site is
  rebuilt on a schedule and when a listing is taken down (backend
  config/seo.py: request_site_rebuild), so closed listings drop out.
*/
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DIST = join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
const SITE = (process.env.SITE_URL || "").replace(/\/$/, "");
const API = (process.env.PRERENDER_API_URL || "").replace(/\/$/, "");
const MAX_LISTINGS = Number(process.env.PRERENDER_MAX_LISTINGS || 2000);
const CONCURRENCY = 6;

const ROLE_TYPES = { internship: "Internship", graduate_programme: "Graduate programme", entry_level: "Entry-level role", graduate_school: "Graduate school" };
const WORK_MODES = { on_site: "On site", hybrid: "Hybrid", remote: "Remote" };
const DEFAULT_DESCRIPTION =
  "Internships, graduate programmes and entry-level roles for students and recent graduates. Keep your transcripts and certificates in one place and apply with them.";

// --- small helpers -----------------------------------------------------------

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const clip = (s, n) => {
  const t = String(s ?? "").replace(/\s+/g, " ").trim();
  return t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t;
};
const abs = (path) => (SITE ? `${SITE}${path}` : path);
const httpUrl = (u) => (typeof u === "string" && /^https?:\/\//i.test(u) ? u : null);
// JSON inside <script> must not be able to close the tag.
const jsonLd = (obj) => `<script type="application/ld+json">${JSON.stringify(obj).replace(/</g, "\\u003c")}</script>`;

async function getJson(path, { attempts = 4, timeout = 90_000 } = {}) {
  let lastError;
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(`${API}${path}`, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(timeout) });
      if (res.status === 404) return null;
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return await res.json();
    } catch (err) {
      lastError = err;
      // A sleeping free-plan API takes up to a minute to wake: wait and retry.
      await new Promise((r) => setTimeout(r, 5_000 * (i + 1)));
    }
  }
  throw new Error(`${path}: ${lastError?.message}`);
}

async function mapLimit(items, limit, fn) {
  const out = new Array(items.length);
  let next = 0;
  await Promise.all(
    Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (next < items.length) {
        const i = next++;
        out[i] = await fn(items[i]).catch((err) => {
          console.warn(`  skipped: ${err.message}`);
          return null;
        });
      }
    }),
  );
  return out;
}

// --- page assembly -----------------------------------------------------------

function page(template, { path, title, description, image, type = "website", body, structured = [] }) {
  const fullTitle = title ? `${title} | SimplyFind` : "SimplyFind: internships and graduate roles";
  const desc = clip(description || DEFAULT_DESCRIPTION, 160);
  const img = httpUrl(image);
  const head = [
    `<title>${esc(fullTitle)}</title>`,
    SITE && `<link rel="canonical" href="${esc(abs(path))}" />`,
    `<meta property="og:site_name" content="SimplyFind" />`,
    `<meta property="og:type" content="${type}" />`,
    `<meta property="og:title" content="${esc(title || "SimplyFind")}" />`,
    `<meta property="og:description" content="${esc(desc)}" />`,
    SITE && `<meta property="og:url" content="${esc(abs(path))}" />`,
    img && `<meta property="og:image" content="${esc(img)}" />`,
    `<meta name="twitter:card" content="${img ? "summary_large_image" : "summary"}" />`,
    ...structured.map(jsonLd),
  ].filter(Boolean).join("\n    ");

  return template
    .replace(/<title>[\s\S]*?<\/title>/, "")
    .replace(/<meta name="description"[^>]*>/, `<meta name="description" content="${esc(desc)}" />`)
    .replace("</head>", `    ${head}\n  </head>`)
    .replace('<div id="root"></div>', `<div id="root">${body}</div>`);
}

const shell = (inner) => `<main style="max-width:72rem;margin:0 auto;padding:2rem 1rem;font-family:system-ui,sans-serif;line-height:1.6">
<nav><a href="/">SimplyFind</a> · <a href="/opportunities">Find roles</a> · <a href="/companies/join">For employers</a></nav>${inner}</main>`;

function sectionsHtml(listing) {
  if (!listing.sections?.length) return listing.description ? `<p>${esc(listing.description)}</p>` : "";
  return listing.sections
    .map((s) => {
      const blocks = (s.blocks || [])
        .map((b) => (b.type === "li" ? `<li>${esc(b.text)}</li>` : b.type === "h" ? `<h3>${esc(b.text)}</h3>` : `<p>${esc(b.text)}</p>`))
        .join("")
        .replace(/(<li>[\s\S]*?<\/li>)+/g, (m) => `<ul>${m}</ul>`);
      return `<section><h2>${esc(s.title)}</h2>${blocks}</section>`;
    })
    .join("");
}

function sectionsText(listing) {
  if (!listing.sections?.length) return listing.description || "";
  return listing.sections.map((s) => [s.title, ...(s.blocks || []).map((b) => b.text)].join("\n")).join("\n\n");
}

function jobPosting(o) {
  const org = o.company?.name || o.organization;
  const remote = o.work_mode === "remote";
  const employment = o.role_type === "internship" ? "INTERN" : o.employment_type === "part_time" ? "PART_TIME" : o.employment_type === "full_time" ? "FULL_TIME" : undefined;
  const parts = (o.location || "").split(",").map((p) => p.replace(/\(.*?\)/g, "").trim()).filter(Boolean);
  return {
    "@context": "https://schema.org",
    "@type": "JobPosting",
    title: o.title,
    description: sectionsText(o).slice(0, 5000) || o.title,
    datePosted: o.published_at || undefined,
    validThrough: o.application_deadline || undefined,
    employmentType: employment,
    hiringOrganization: org ? {
      "@type": "Organization",
      name: org,
      ...(o.company?.slug ? { sameAs: abs(`/companies/${o.company.slug}`) } : {}),
      ...(httpUrl(o.company?.logo_url) ? { logo: o.company.logo_url } : {}),
    } : undefined,
    ...(remote ? { jobLocationType: "TELECOMMUTE" } : {}),
    ...(parts.length && !remote ? {
      jobLocation: { "@type": "Place", address: { "@type": "PostalAddress", addressLocality: parts[0], addressCountry: parts[parts.length - 1] } },
    } : {}),
    experienceRequirements: o.experience_years_max ? { "@type": "OccupationalExperienceRequirements", monthsOfExperience: o.experience_years_max * 12 } : "no requirements",
    directApply: o.application_method === "in_app",
    url: abs(`/opportunities/${o.id}`),
  };
}

function listingFacts(o) {
  return [ROLE_TYPES[o.role_type], WORK_MODES[o.work_mode], o.location, o.application_deadline && `Closes ${o.application_deadline.slice(0, 10)}`]
    .filter(Boolean).map(esc).join(" · ");
}

// --- main ----------------------------------------------------------------------

async function write(path, html) {
  const file = path === "/" ? join(DIST, "index.html") : join(DIST, ...path.split("/").filter(Boolean), "index.html");
  await mkdir(dirname(file), { recursive: true });
  await writeFile(file, html);
}

async function main() {
  const template = await readFile(join(DIST, "index.html"), "utf8");
  // The shell every client-side route falls back to (render.yaml rewrites /* to it).
  await writeFile(join(DIST, "app.html"), template);
  await writeFile(join(DIST, "robots.txt"), [
    "User-agent: *",
    ...["/profile", "/applications", "/saved", "/company", "/account", "/claim", "/verify-email", "/reset-password", "/login", "/register"].map((p) => `Disallow: ${p}`),
    "Allow: /",
    SITE && `\nSitemap: ${SITE}/sitemap.xml`,
    "",
  ].filter((l) => l !== "").join("\n") + "\n");

  await write("/companies/join", page(template, {
    path: "/companies/join",
    title: "Hire students and recent graduates",
    description: "Post internships, graduate programmes and entry-level roles. Applicants come with their studies, skills and verified documents.",
    body: shell("<h1>Hire students and recent graduates, without the paperwork</h1><p>Post roles, collect applications with verified documents, and run campus recruitment drives.</p>"),
  }));

  if (!API) {
    console.warn("prerender: PRERENDER_API_URL is not set; wrote the static pages only.");
    await write("/", page(template, { path: "/", body: shell("<h1>Find your first role. Apply without the paperwork.</h1>") }));
    return;
  }

  console.log(`prerender: reading ${API}`);
  let listings = [];
  let stats = null;
  let categories = [];
  try {
    [stats, categories] = await Promise.all([getJson("/api/opportunities/stats/"), getJson("/api/opportunities/categories/")]);
    for (let pageNo = 1; listings.length < MAX_LISTINGS; pageNo++) {
      const data = await getJson(`/api/opportunities/?page_size=100&page=${pageNo}`);
      listings.push(...(data?.results || []));
      if (!data?.next) break;
    }
  } catch (err) {
    // Never fail the deploy because the API is down: the app still works.
    console.warn(`prerender: API unavailable (${err.message}); wrote the static pages only.`);
    await write("/", page(template, { path: "/", body: shell("<h1>Find your first role. Apply without the paperwork.</h1>") }));
    return;
  }
  listings = listings.slice(0, MAX_LISTINGS);

  // Home and role list
  const latest = listings.slice(0, 12);
  const cards = (items) => `<ul>${items.map((o) => `<li><a href="/opportunities/${o.id}">${esc(o.title)}</a> · ${esc(o.company?.name || o.organization)} · ${listingFacts(o)}</li>`).join("")}</ul>`;
  await write("/", page(template, {
    path: "/",
    structured: [{ "@context": "https://schema.org", "@type": "WebSite", name: "SimplyFind", url: abs("/") }],
    body: shell(`<h1>Find your first role. Apply without the paperwork.</h1><p>${esc(DEFAULT_DESCRIPTION)}</p>
${stats ? `<p>${stats.live} open roles from ${stats.organizations} organisations.</p>` : ""}<h2>Latest roles</h2>${cards(latest)}
<h2>Browse by field</h2><ul>${categories.filter((c) => c.live_count).map((c) => `<li><a href="/opportunities?category=${esc(c.slug)}">${esc(c.name)}</a> (${c.live_count})</li>`).join("")}</ul>`),
  }));
  await write("/opportunities", page(template, {
    path: "/opportunities",
    title: "Find roles",
    description: `${listings.length} internships, graduate programmes and entry-level roles for students and recent graduates.`,
    body: shell(`<h1>Find roles</h1>${cards(listings.slice(0, 100))}`),
  }));

  // One page per open role, from the detail endpoint (it has the sections).
  const details = await mapLimit(listings, CONCURRENCY, (o) => getJson(`/api/opportunities/${o.id}/`, { attempts: 2, timeout: 30_000 }));
  let written = 0;
  for (const o of details) {
    if (!o) continue;
    const org = o.company?.name || o.organization;
    await write(`/opportunities/${o.id}`, page(template, {
      path: `/opportunities/${o.id}`,
      title: org ? `${o.title}, ${org}` : o.title,
      description: o.description,
      image: o.image_url,
      type: "article",
      structured: [jobPosting(o)],
      body: shell(`<article><p>${esc(org)}</p><h1>${esc(o.title)}</h1><p>${listingFacts(o)}</p>${sectionsHtml(o)}
<p><a href="/opportunities/${o.id}">${o.application_method === "in_app" ? "Apply on SimplyFind" : "How to apply"}</a></p></article>`),
    }));
    written++;
  }

  // Companies with open roles (there's no public company list endpoint).
  const slugs = [...new Set(listings.map((o) => o.company?.slug).filter(Boolean))];
  const companies = await mapLimit(slugs, CONCURRENCY, (slug) => getJson(`/api/companies/${encodeURIComponent(slug)}/`, { attempts: 2, timeout: 30_000 }));
  let companyPages = 0;
  for (const data of companies) {
    if (!data?.company) continue;
    const c = data.company;
    await write(`/companies/${c.slug}`, page(template, {
      path: `/companies/${c.slug}`,
      title: `${c.name}: jobs and internships`,
      description: c.description || `Open roles at ${c.name} for students and recent graduates.`,
      image: c.logo_url,
      structured: [{
        "@context": "https://schema.org", "@type": "Organization", name: c.name, url: abs(`/companies/${c.slug}`),
        ...(httpUrl(c.website) ? { sameAs: c.website } : {}), ...(httpUrl(c.logo_url) ? { logo: c.logo_url } : {}),
      }],
      body: shell(`<h1>${esc(c.name)}</h1><p>${esc([c.industry, c.location].filter(Boolean).join(" · "))}</p><p>${esc(c.description)}</p>
<h2>Open roles</h2>${cards(data.jobs || [])}`),
    }));
    companyPages++;
  }
  console.log(`prerender: ${written} role pages, ${companyPages} company pages, home, role list, employer page.`);
}

main().catch((err) => {
  // A broken pre-render must not take the site down: log it, keep the SPA.
  console.error("prerender failed:", err);
  process.exitCode = 0;
});
