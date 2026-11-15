# SimplyFind API

Everything is under `/api/`. JSON unless noted. Signed-in requests use the
`sf_access` / `sf_refresh` HttpOnly cookies set by sign-in; every POST, PATCH
and DELETE sent with cookies needs the `X-CSRFToken` header (get the token
from `GET /api/auth/csrf/`). An `Authorization: Bearer` header also works,
for scripts.

Errors are `{"field": ["message"]}` or `{"detail": "message"}`. Two codes the
website should handle everywhere:

| `code` (403) | Meaning | What to show |
|---|---|---|
| `email_not_verified` | Applying or creating a company needs a confirmed email | "Check your inbox" + resend button |
| `mfa_setup_required` / `mfa_required` | Staff and company team members need two-step sign-in | Send to two-step setup / sign in again |

## Who uses what

| Person | Main screens |
|---|---|
| Student or recent graduate | Sign up, guided profile (4 steps), documents and certificates, browse roles, apply, my applications, who opened my files |
| Company team (owner, admin, recruiter) | Company profile, team, jobs and their questions, applicants (filters, bulk status, CSV or print), recruitment drives and the desk |
| Moderator / admin | Django admin: approve companies and listings, ingestion sources |

## Accounts: `/api/auth/`

| Method | Path | Purpose |
|---|---|---|
| GET | `csrf/` | Sets the CSRF cookie, returns `{csrfToken}` |
| POST | `register/` | `{name, email, password, drive?}` -> 201 `{user}` + cookies; sends the confirmation email. `drive` is a drive code from a QR link |
| POST | `login/` | `{email, password}` -> `{user}` + cookies, or `{mfa_required, mfa_token}` |
| POST | `mfa/login/` | `{mfa_token, code}` (6 digits or a recovery code) -> `{user}` + cookies |
| POST | `google/` | `{credential}` Google ID token; same answers as `login/` |
| POST | `refresh/` | New access cookie (refresh token from the cookie or body) |
| POST | `logout/` | Revokes the refresh token, clears cookies |
| POST | `verify-email/` | `{token}` from the emailed link |
| POST | `verify-email/resend/` | Sends the link again |
| POST | `mfa/setup/` | `{password}` -> `{secret, otpauth_uri, qr_svg}` |
| POST | `mfa/enable/` | `{code}` -> `{recovery_codes}` (shown once) |
| POST | `mfa/disable/` | `{password, code}` |
| GET/PATCH | `me/` | The signed-in user; PATCH `name`, `profile_picture`. Read: user (`email_verified`, `mfa_enabled`, `mfa_required`, `role`, `company`...) |
| POST | `me/delete/` | Deactivates now, deletes after 14 days |
| POST | `password-reset/`, `password-reset/confirm/` | Reset by email |

## Student profile: `/api/profile/`

| Method | Path | Purpose |
|---|---|---|
| GET/PATCH | `` | Profile + `progress` `{steps: [{key, label, done, missing}], completeness, next_step}`. Steps: `about` (name, date_of_birth, country, phone, city), `studies` (status `student`/`graduate`, institution, programme, field slug, graduation_year), `skills` (skills, languages, headline), `documents` |
| GET/POST | `documents/` | Vault. POST multipart `{file, kind, title}`; kinds `transcript`, `certificate`, `cv`, `recommendation`, `id_document`, `other`. PDF, JPG or PNG, scanned |
| PATCH/DELETE | `documents/<id>/` | Rename or delete |
| GET | `documents/<id>/file/` | Download your own file |
| GET/POST | `credentials/` | Online certificates `{url, title, provider?, issuer?, issued_on?}`. `check_status`: `recognised_link` (a certificate page on Coursera, edX, Credly or LinkedIn Learning), `verified` (an Open Badge checked with its issuer), `failed`, `unchecked` (other sites) |
| DELETE | `credentials/<id>/` | Remove |
| POST | `credentials/<id>/check/` | Check again |
| GET | `access-log/` | Which hiring teams opened my files, and when |
| GET | `eligibility/<job id>/` | `{eligible, reasons}` before showing the apply form |

Date of birth is never shown to companies. It only decides the 18+ rule.

## Roles: `/api/opportunities/`

| Method | Path | Purpose |
|---|---|---|
| GET | `` | Live roles. Filters below; lists are comma-separated and match any value, unknown values are ignored. Graduate school only appears when asked for by `role_type` |
| GET | `<id>/` | One role, with `requirements` (the application questions) and `has_applied` |
| GET | `categories/` | Fields of work (the website's "Industry" filter), with `live_count` |
| GET | `locations/` | Places with open roles, busiest first: `[{name, count}]` (the country part of each listing's location) |
| GET | `stats/` | Landing-page numbers |
| POST | `<id>/save/`, DELETE `<id>/unsave/`, GET `saved/` | Bookmarks |

List filters:

| Parameter | Values |
|---|---|
| `search` | Text in the title, organisation, description or location |
| `category` | Category slugs |
| `role_type` | `internship`, `graduate_programme`, `entry_level`, `graduate_school` |
| `career_level` | `no_experience`, `some_experience`, `early_career` (0, 1 or 2 years of experience asked for) |
| `work_mode` | `on_site`, `hybrid`, `remote` |
| `employment_type` | `full_time`, `part_time` (listings that don't say are left out when this is set) |
| `location` | Up to 5 terms; the location contains any of them (`Ghana,Kenya`) |
| `deadline` | `week`, `month` (closes within 7 / 30 days), `rolling` (no deadline) |
| `posted_within` | Days, 1 to 365 |
| `duration` | Internship length: `short` (up to 3 months), `medium` (4 to 6), `long` (7+) |
| `graduation_year` | Roles open to graduates of that year |
| `paid`, `apply_on_site`, `verified`, `open_to_minors` | `true`: paid only; apply on SimplyFind; verified companies; accepts under-18s |
| `ordering` | `-published_at` (default), `application_deadline` |

Listings carry `employment_type` (`full_time`, `part_time` or blank). Companies set it on their jobs; ingestion
infers it when the listing says only one of "full-time" or "part-time".

## Applying: `/api/applications/`

| Method | Path | Purpose |
|---|---|---|
| GET | `` | My applications and their status |
| POST | `` | Multipart: `opportunity`, `consent=true`, and one `answer_<requirement id>` per question. For a file question send a new file, or `vault:<document id>` to attach a copy of a vault document. Refused with `eligibility` reasons when the student isn't eligible |
| POST | `<id>/withdraw/` | Withdraw; answers and files are deleted |
| GET | `answers/<id>/file/` | A file in an application (the applicant, or the hiring team; the team's opens are logged) |

## Companies: `/api/companies/`

| Method | Path | Purpose |
|---|---|---|
| POST | `` | Register a company (starts pending review) |
| GET/PATCH | `me/` | Company profile |
| POST | `me/logo/` | Logo upload |
| GET/POST | `me/jobs/` | Jobs, with `requirements`, `role_type`, `graduation_year_min/max`, `experience_years_max` (at most 2), `is_paid`, `work_mode`, `employment_type`, `duration_months`, `accepts_minors` |
| GET/PATCH | `me/jobs/<id>/`, POST `me/jobs/<id>/close/` | Edit or close |
| GET | `me/jobs/<id>/applications/` | Applicants. Filters: `status` (comma list), `graduation_year`, `field`, `applicant_status`, `verified_certificates=true`, `q`. Each applicant has `profile` (studies, skills), `credentials`; `email` and `phone` only once shortlisted or hired |
| POST | `me/jobs/<id>/applications/bulk/` | `{ids, status}`: each applicant is emailed |
| GET | `me/jobs/<id>/applications/export.csv`, `.../print/` | Applicant list as CSV or a printable page, same filters; every export is logged |
| PATCH | `me/applications/<id>/` | `{status, company_note}` |
| GET, POST, PATCH, DELETE | `me/team/...` | Team members and invitations |
| GET | `<slug>/` | Public company page |

## Recruitment drives: `/api/drives/`

A drive is a company's recruiting day (a careers fair, a university visit).

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `mine/` | The company's drives `{name, location, starts_on, ends_on, description, opportunities: [job ids]}` -> with `code`, `public_url`, counts |
| GET/PATCH/DELETE | `mine/<id>/` | One drive |
| GET | `mine/<id>/qr.png` | QR code of the public link, for posters and the desk |
| GET/POST | `mine/<id>/students/` | Desk signups. POST `{name, email, consent: true, institution?, programme?, graduation_year?, status?, phone?, country?, date_of_birth?}` creates the account without a password and emails the student a claim link |
| POST | `mine/<id>/students/<reg id>/documents/` | Scan a document for that student, on the day, before they claim |
| POST | `mine/<id>/students/<reg id>/resend/` | Send the claim email again |
| GET/POST | `claim/` | Student: GET `?token=` shows what was set up; POST `{token, password}` claims it and signs in |
| GET | `<CODE>/` | Public drive page with its open roles (what the QR code opens, at `/d/<CODE>` on the website) |

Unclaimed desk accounts are deleted after 14 days.
