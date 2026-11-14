# Deploying SimplyFind

Three Render services, all in [`render.yaml`](../render.yaml):

| Service | What it is |
|---|---|
| `simplyfind-web` | The website: a static site (React app plus pre-rendered public pages) |
| `simplyfind-api` | Django API and admin |
| `simplyfind-clamav` | Virus scanner for uploads, reachable only by the API |

Scheduled jobs (fetching listings, privacy clean-ups, rebuilding the website)
run from GitHub Actions: [`.github/workflows/ingest.yml`](../.github/workflows/ingest.yml).

## First deploy

1. **Database and storage (Supabase).** Create a project. Copy the session
   pooler connection string (`DATABASE_URL`). In Storage, create two buckets:
   a **public** one (profile pictures, logos) and a **private** one
   (transcripts, CVs, certificates), and S3 access keys.
2. **Email (Brevo).** Create an API key and verify the sender address.
3. **Blueprint.** Render dashboard → New → Blueprint → this repository.
   Render asks for every value marked `sync: false`:

   | Service | Variable | Value |
   |---|---|---|
   | api | `SITE_URL` | The website's address, e.g. `https://simplyfind-web.onrender.com` |
   | api | `DATABASE_URL`, `SUPABASE_*`, `BREVO_API_KEY`, `DEFAULT_FROM_EMAIL` | From steps 1 and 2 |
   | api | `DJANGO_SUPERUSER_*` | The first admin (remove the password after the first deploy) |
   | api | `CORS_ALLOWED_ORIGINS`, `AUTH_COOKIE_*`, `GOOGLE_CLIENT_ID`, `APPLICATION_RETENTION_DAYS`, `FRONTEND_DEPLOY_HOOK` | Leave empty for now |
   | web | `SITE_URL` | Same as the API's |
   | web | `PRERENDER_API_URL` | The API's address, e.g. `https://simplyfind-api.onrender.com` |
   | web | `VITE_API_URL`, `VITE_GOOGLE_CLIENT_ID` | Leave empty (see "How the website reaches the API") |

4. **Check the API address.** If Render gave the API a different address
   than `simplyfind-api.onrender.com`, change it in the two `routes` of
   `simplyfind-web` in `render.yaml`, and push.
5. **Two-step sign-in for the admin.** From the API's Shell:
   `python manage.py setup_mfa <admin email>`.
6. **Website rebuilds.** In `simplyfind-web` → Settings → Deploy Hook, copy the
   URL. Put it in the API's `FRONTEND_DEPLOY_HOOK` (taken-down listings leave
   the site at once) and in the GitHub secret `RENDER_FRONTEND_DEPLOY_HOOK`
   (new listings get their pages twice a day). Add `DATABASE_URL` as a
   GitHub secret too, for the scheduled jobs.

## Check it works

- `https://<api>/health/` answers `{"status": "ok"}`.
- The website loads, and `https://<website>/sitemap.xml` lists the roles.
- View the source of a role page: the title and description are in the HTML.
- Create an account, confirm the email from the link, then **save a role**.
  Saving is the first signed-in write: if it fails with "CSRF failed", the
  API's `SITE_URL` doesn't match the website's address exactly.
- **Sign-in rate limits.** Through the `/api` proxy, Render may not pass the
  visitor's IP to the API, so the 10-sign-ins-a-minute limit could count all
  visitors together. Sign in from two different networks within a minute a
  few times. If people get "Too many attempts" together, switch to the direct
  setup below.

## How the website reaches the API

Sign-in uses cookies, so the browser must see the API as the same site as
the website. Two ways, chosen by the website's `VITE_API_URL`:

- **Proxy (default, `VITE_API_URL` empty).** The website forwards `/api/*` to
  the API (the `routes` in `render.yaml`). Works on the free `*.onrender.com`
  addresses. Each API call takes a little longer, and see the rate-limit
  check above.
- **Direct (your own domain).** Website at `simplyfind.org`, API at
  `api.simplyfind.org`:
  1. Add both custom domains in Render and create the DNS records it shows.
  2. API: `SITE_URL=https://simplyfind.org`.
  3. Website: `SITE_URL=https://simplyfind.org`,
     `VITE_API_URL=https://api.simplyfind.org`,
     `PRERENDER_API_URL=https://api.simplyfind.org`, then redeploy it.

  Leave `AUTH_COOKIE_SAMESITE` and `AUTH_COOKIE_DOMAIN` unset in both setups.

## Pre-rendered pages

`npm run build` runs `vite build`, then `scripts/prerender.mjs`, which reads
the API and writes an HTML file for the home page, the role list, every open
role and every company with open roles. They carry their own title,
description, link-preview tags and JobPosting data for search engines. React
replaces their content when it starts. If the API can't be reached during the
build, only the static pages are written and the deploy still succeeds.
