# `apps/ingestion`

Everything about *how* opportunities arrive automatically. It does two
jobs, both without anyone clicking anything:

1. **Fetch** — every active `FetchSource` is fetched on its own schedule
   (default every 6 hours). New items land as `PENDING` opportunities.
2. **Enrich** — for *each* opportunity that has a link (fetched or
   user-submitted), the worker visits the listing page and pulls its
   cover image, summary and organisation name from the page's Open Graph
   tags. That's where the images on the landing page and cards come from.

Fetching never approves anything. Every listing still goes through the
same moderation queue as user submissions.

## Files

| File | Purpose |
|---|---|
| `models.py` | `FetchSource` (config + its own schedule: `fetch_interval_minutes`, `next_fetch_at`, failure count) and `FetchLog` (one row per run) |
| `connectors/base.py` | `BaseConnector` — the interface: `fetch() -> list[dict]` |
| `connectors/job_boards.py` | Greenhouse, Ashby and Workable careers boards via their public job-board APIs |
| `classify.py` | Per-item category from feed tags/title; deadline from "Deadline: …" in the text |
| `connectors/rss_connector.py` | RSS 2.0 **and** Atom, standard library only. Strips HTML from descriptions, picks up `<enclosure>`/`<media:content>` images |
| `connectors/__init__.py` | Registry mapping `FetchSource.connector_type` → connector class |
| `services.py` | `fetch_source(source)` — run one source, de-dupe, create `Opportunity` rows, write the `FetchLog`, schedule the next run |
| `enrichment.py` | `enrich_opportunity(opp)` — read the listing page's meta tags, fill blanks only; swap an aggregator link for the organiser's |
| `organizer.py` | `find_organizer_url(html, page_url)` — the organiser's apply/official link inside an aggregator's article |
| `sections.py` | `extract_sections(html)` — the description split into About the organisation, Eligibility, Benefits, How to apply … |
| `http.py` | Outbound HTTP: User-Agent, timeouts, size caps, and the SSRF guard for user-supplied links |
| `scheduler.py` | One worker cycle: claim due sources + pending enrichment (row locks with `SKIP LOCKED`), run them |
| `worker.py` | The loop; also the optional in-process thread for `runserver` |
| `management/commands/run_ingestion_worker.py` | `python manage.py run_ingestion_worker` — production worker process |
| `management/commands/fetch_opportunities.py` | Fetch all (or one) source right now, ignoring the schedule |
| `apps.py` | Starts the in-process worker under `runserver` when `INGESTION_AUTOSTART` is on |
| `admin.py` | Sources (schedule, health, "Fetch now", "Fetch on next cycle"), read-only fetch history |

## Running it

**Development** — nothing extra. With `DEBUG=True`, `INGESTION_AUTOSTART`
defaults to on and `python manage.py runserver` starts the worker in a
background thread. Logs look like:

```
INFO apps.ingestion.worker: Started in-process ingestion worker (INGESTION_AUTOSTART=True)
INFO apps.ingestion.scheduler: Fetched Opportunity Desk: success (found 20, new 20)
INFO apps.ingestion.worker: Ingestion cycle: {'sources_fetched': 1, 'opportunities_created': 20, 'opportunities_enriched': 20}
```

**Production** — run the worker as its own process next to the web
server (see `backend/Procfile`):

```bash
web:    gunicorn config.wsgi:application
worker: python manage.py run_ingestion_worker
```

Set `INGESTION_AUTOSTART=False` in production so gunicorn workers don't
also start threads. (It's harmless if they do — sources are claimed with
row locks, so nothing is fetched twice — just wasteful.)

**No long-running process available?** Run one cycle from cron instead:

```bash
*/10 * * * * cd /path/to/backend && venv/bin/python manage.py run_ingestion_worker --once
```

## Scheduling rules

- A source is **due** when `is_active` and `next_fetch_at` is empty or in
  the past. New sources are fetched on the very next cycle.
- After a successful run: `next_fetch_at = now + fetch_interval_minutes`.
- After a failure: retry in 15 min, then 30, 60, … capped at 24 h.
  `consecutive_failures` and `last_error` show in the admin.
- "Fetch now" in the admin runs immediately and reschedules normally.
  "Fetch on the worker's next cycle" just clears `next_fetch_at`.

## Enrichment rules

- Runs for every opportunity with `enrichment_status = pending` — which
  includes every existing row after migrating, so old listings get
  images too.
- **Fills blanks only.** An image, organisation or a real description
  (40+ characters) that someone provided is never replaced.
- Saves with `update_fields`, so it can't undo a moderator's approval
  that happens at the same moment.
- Network errors retry up to 3 times, 10 minutes apart, then `failed`.
  Links that can never work (private/internal hosts, PDFs, non-HTML)
  are marked `skipped` immediately.
- Admin action **"Re-fetch image and summary"** re-queues selected rows.

### Organiser links, not aggregator links

RSS sources are aggregators: an item's `<link>` is their write-up, not the
opportunity. Fetched RSS rows store that link in `listing_url` too, and
while `opportunity_url` still equals it, enrichment looks through the
article body for the organiser's link — anchor text like "Click here to
apply", "Official Webpage", a spelled-out URL under "How to apply", or a
generic "here"/"ici" in a sentence about applying — skipping share
buttons, nav/footer/sidebar links and links back to the aggregator.
When one is found it becomes `opportunity_url`; otherwise the listing
page stays. The organisation name then comes from the organiser's home
page `og:site_name` (not from ATS/form hosts like Workable or Jotform),
never the aggregator's or the post author's (`<dc:creator>`). Job-board
connectors already link to the employer's posting and are left alone, as
are links a moderator has edited. Enrichment always reads the article at
`listing_url`, even after the link has been swapped.

Checked against every configured feed (October 2026): 23 of 28 recent
items resolved; the rest were paywalled (Funds for NGOs) or email-only.

### Description sections

`Opportunity.sections` holds the description split into named sections,
shown in this order on the listing page: About this opportunity, About
the organisation, Eligibility, What the role involves, Benefits,
Required documents, How to apply, Deadline and key dates — plus up to
four of the source's own headings that fit none of those. Each section is
a list of text blocks (paragraph, bullet, sub-heading); never HTML.

`ingestion/sections.py` builds them from the source's HTML: the feed's
`<content:encoded>`, the Greenhouse/Ashby/Workable job description, or —
during enrichment — the article body of the listing page. Headings are
matched by wording in English, French and Spanish ("Who can apply?",
"Requisitos", "Comment postuler"…), whether they're `<h2>`s, bold
paragraphs or "**Deadline:** 17 Nov" labels; numbered sub-points stay in
their section; share boxes, related posts and comments are skipped.
When the article has no "About the organisation", the organiser's home
page meta description fills it. A "Deadline: …" line in the sections
sets `application_deadline` if nothing else did.

Like everything else, sections only fill blanks: a refetch adds them to
listings stored without them, and never replaces ones a moderator edited
(Django admin → "Description sections"). Submitters fill the same
sections through optional fields on the submit form.

Measured on a live run (October 2026): sections on 47 of 48 aggregator
listings and on every Greenhouse, Ashby and Workable job.

### Why the SSRF guard exists

Anyone who can submit an opportunity chooses its URL, and the worker
then requests that URL from our server. `http.fetch_public_html` refuses
any URL that resolves to a loopback, private, link-local (e.g. the cloud
metadata service at `169.254.169.254`) or otherwise non-public address,
and re-checks after every redirect (redirects are followed manually for
that reason). Feed URLs are entered by admins and aren't restricted.

## De-duplication

An item is skipped if an `Opportunity` with the same `opportunity_url`
or `listing_url` already exists (both indexed; `listing_url` matters once
enrichment has swapped in the organiser link), or — for items without
a link — if the same source already produced the same title. Duplicates
inside a single feed response are also collapsed.

Two aggregators posting the same call resolve to the same organiser
link. When enrichment finds that link already on a listing from a
*different* source with a near-identical title, the newer copy is
rejected automatically ("Automatic: duplicate of #N") while still
pending. The source-and-title check matters: one source often points
several different jobs at a single shared application form.

## Adding a new source

1. RSS or Atom: no code. Add a `FetchSource` in `/admin/` with
   `connector_type = rss`, the feed URL, a category, and an interval.
   Paste the *feed* URL (often `<site>/feed/`), not the homepage — a web
   page fails with "returned a web page, not an RSS/Atom feed".
2. A company careers page on Greenhouse, Ashby or Workable: no code. Pick
   that connector type and paste the board URL
   (`https://job-boards.greenhouse.io/<company>`,
   `https://jobs.ashbyhq.com/<company>`, `https://apply.workable.com/<company>/`).
   Use **include keywords** (e.g. `Ghana, Nigeria, Kenya, Remote`) to keep
   only relevant roles from employers that hire worldwide.
3. `python manage.py setup_fetch_sources` adds the researched starter list
   (aggregators + Africa-hiring employers); safe to re-run.
4. A new kind of source (JSON API, HTML page without a feed): write one
   class implementing `BaseConnector.fetch()`, register it in
   `connectors/__init__.py`, add a value to `FetchSource.ConnectorType`.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `INGESTION_AUTOSTART` | `DEBUG` | Start the worker inside `runserver` |
| `INGESTION_WORKER_INTERVAL_SECONDS` | `60` | Pause between cycles |
| `INGESTION_SOURCE_BATCH` | `10` | Max sources fetched per cycle |
| `INGESTION_ENRICH_BATCH` | `25` | Max opportunities enriched per cycle |
| `INGESTION_USER_AGENT` | `EELBot/1.0 (+repo URL)` | Sent with every request |

## Known limits

- Images are hot-linked from the listing's own site. If a site blocks
  hot-linking, the card falls back to the designed placeholder. Copying
  images to our own storage would need the media-storage backend that
  profile pictures also need before production.
- DNS rebinding (a host that resolves public for the check, private for
  the connection) isn't defended against; that needs a pinned-IP
  transport or an egress proxy.
