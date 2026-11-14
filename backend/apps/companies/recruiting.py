"""
Working through a job's applicants: filters, bulk status changes, and the
applicant list as CSV or a printable page (each export is logged).

Exports follow the same privacy rules as the dashboard: email and phone
only for shortlisted or hired applicants, never date of birth, and no
answers or files (those stay on the site, where opening them is logged).
"""

import csv
import io

from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.utils.html import escape
from rest_framework.exceptions import ValidationError

from apps.documents.models import Credential

from .models import Application, ExportLog
from .serializers import CONTACT_VISIBLE_STATUSES
from .services import set_application_status

MAX_BULK = 200
BULK_STATUSES = {Application.Status.REVIEWING, Application.Status.SHORTLISTED,
                 Application.Status.REJECTED, Application.Status.HIRED}


def filter_applications(queryset, params):
    """?status=, ?graduation_year=, ?field=<slug>, ?applicant_status=student|graduate,
    ?verified_certificates=true, ?q= (name, school or programme)."""
    if status := params.get("status"):
        statuses = [s for s in status.split(",") if s in Application.Status.values]
        queryset = queryset.filter(status__in=statuses)
    if year := params.get("graduation_year"):
        try:
            queryset = queryset.filter(applicant__student_profile__graduation_year=int(year))
        except ValueError:
            raise ValidationError({"graduation_year": "Use a year, like 2026."})
    if field := params.get("field"):
        queryset = queryset.filter(applicant__student_profile__field__slug=field)
    if kind := params.get("applicant_status"):
        queryset = queryset.filter(applicant__student_profile__status=kind)
    if params.get("verified_certificates") in ("true", "1"):
        verified = Credential.objects.filter(owner=OuterRef("applicant"), check_status=Credential.Check.VERIFIED)
        queryset = queryset.filter(Exists(verified))
    if q := (params.get("q") or "").strip():
        queryset = queryset.filter(
            Q(applicant__name__icontains=q)
            | Q(applicant__student_profile__institution__icontains=q)
            | Q(applicant__student_profile__programme__icontains=q)
        )
    return queryset


@transaction.atomic
def bulk_set_status(job, ids, status: str) -> int:
    if status not in BULK_STATUSES:
        raise ValidationError({"status": "Choose reviewing, shortlisted, not selected or hired."})
    if not isinstance(ids, list) or not ids or len(ids) > MAX_BULK:
        raise ValidationError({"ids": f"Choose between 1 and {MAX_BULK} applications."})
    try:
        ids = {int(i) for i in ids}
    except (TypeError, ValueError):
        raise ValidationError({"ids": "Unknown applications."})
    applications = list(
        job.applications.select_for_update(of=("self",)).exclude(status=Application.Status.WITHDRAWN)
        .filter(pk__in=ids).select_related("applicant", "opportunity__company")
    )
    if len(applications) != len(ids):
        raise ValidationError({"ids": "Some of these applications aren't on this job."})
    changed = 0
    for application in applications:
        if application.status != status:
            set_application_status(application, {"status": status})  # emails the applicant
            changed += 1
    return changed


COLUMNS = ["Name", "Status", "Applied", "School or university", "Programme", "Field", "Graduation year",
           "Student or graduate", "Skills", "Verified certificates", "Email", "Phone"]


def _safe(value) -> str:
    """Spreadsheets run cells starting with = + - @ as formulas (CSV injection)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def rows(applications):
    for app in applications:
        user = app.applicant
        profile = _profile(user)
        visible = app.status in CONTACT_VISIBLE_STATUSES
        verified = [c.title for c in user.credentials.all() if c.check_status == Credential.Check.VERIFIED]
        yield [
            user.name, app.get_status_display(), app.submitted_at.date().isoformat(),
            profile.institution if profile else "", profile.programme if profile else "",
            profile.field.name if profile and profile.field else "",
            profile.graduation_year if profile and profile.graduation_year else "",
            profile.get_status_display() if profile and profile.status else "",
            ", ".join(profile.skills) if profile else "",
            ", ".join(verified),
            user.email if visible else "",
            (profile.phone if profile else "") if visible else "",
        ]


def _profile(user):
    from apps.profiles.models import StudentProfile
    try:
        return user.student_profile
    except StudentProfile.DoesNotExist:
        return None


def log_export(request, company, job, fmt, count, params) -> None:
    ExportLog.objects.create(
        company=company, user=request.user, user_name=request.user.name[:120],
        opportunity=job, job_title=job.title[:300], format=fmt, row_count=count,
        filters={k: v for k, v in params.items() if k != "format"},
    )


def to_csv(applications) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    for row in rows(applications):
        writer.writerow([_safe(cell) for cell in row])
    return "﻿" + out.getvalue()  # BOM so Excel reads names in UTF-8


def to_print_html(job, applications) -> str:
    head = "".join(f"<th>{escape(c)}</th>" for c in COLUMNS)
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>" for row in rows(applications)
    )
    title = escape(f"Applicants: {job.title}")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='robots' content='noindex'><title>{title}</title>"
        "<style>body{font:12px system-ui,sans-serif;margin:24px;color:#111}"
        "table{border-collapse:collapse;width:100%}th,td{border:1px solid #999;padding:4px 6px;"
        "text-align:left;vertical-align:top}th{background:#eee}@media print{body{margin:0}}</style>"
        f"</head><body><h1>{title}</h1><p>{escape(job.company.name)}. Confidential: personal data of applicants. "
        "Don't share or leave printed copies lying around.</p>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></body></html>"
    )
