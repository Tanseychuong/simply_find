"""
Company business rules, kept out of the views so they're testable and so
the Django admin's actions, the moderator API and the company API share one
path (including the emails each action sends).
"""

import re

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.documents.uploads import clean_upload_or_400
from apps.opportunities.models import Opportunity

from . import notifications
from .models import (
    Application, ApplicationAnswer, ApplicationRequirement, Company, CompanyInvitation, CompanyMembership,
)

Role = CompanyMembership.Role

YES_NO = {"yes", "no"}

# Application questions about protected characteristics are unlawful to ask
# in many countries. A job asking about any of these is held for a human
# moderator, even from a verified company. Deliberately conservative: a
# false positive costs one review; a false negative publishes it unchecked.
SENSITIVE_TERMS = {
    "age": r"\bage\b|\bhow old\b|date of birth|\bdob\b|year of birth|birth ?date",
    "gender or sex": r"\bgender\b|\bsex\b",
    "religion": r"religio|\bfaith\b|\bchurch\b|\bmosque\b",
    "ethnicity or race": r"ethnic|\brace\b|\btribe\b|\btribal\b|skin colou?r",
    "marital or family status": r"marital|married|\bspouse\b|pregnan|children|\bkids\b",
    "disability or health": r"disabilit|medical|\bhealth\b|\bhiv\b",
    "sexual orientation": r"orientation|\bgay\b|lesbian",
    "political views": r"politic",
    "photo of the applicant": r"\bphoto|\bpicture\b|\bselfie\b|headshot",
    "nationality": r"nationality|citizenship",
}


def flagged_terms(requirements) -> list[str]:
    """Which protected characteristics these requirement labels/help texts ask about."""
    text = " ".join(f"{r.get('label', '')} {r.get('help_text', '')}" if isinstance(r, dict)
                    else f"{r.label} {r.help_text}" for r in requirements).lower()
    return [name for name, pattern in SENSITIVE_TERMS.items() if re.search(pattern, text)]


# --- Company accounts -------------------------------------------------------

@transaction.atomic
def register_company(user, data) -> Company:
    if CompanyMembership.objects.filter(user=user).exists():
        raise ValidationError({"detail": "You're already on a company's team. Leave it before creating another."})
    try:
        with transaction.atomic():
            return Company.objects.create_with_owner(
                user, status=Company.Status.PENDING, terms_accepted_at=timezone.now(), **data,
            )
    except IntegrityError:  # double submit raced past the check above
        raise ValidationError({"detail": "You're already on a company's team."})


# --- Teams ------------------------------------------------------------------

def _lock_company(company) -> Company:
    """Serialise team changes for one company (role changes, removals,
    joins), so two at once can't both pass the 'keeps an owner' check."""
    return Company.objects.select_for_update().get(pk=company.pk)


def _active_owner_count(company) -> int:
    # Owners waiting for their account to be deleted can't act, so they
    # don't count towards "the company still has an owner".
    return company.memberships.filter(role=Role.OWNER, user__is_active=True).count()


def reassign_company_jobs(user, company: Company) -> None:
    """Jobs a person posted for a company stay with the company when they
    leave it or their account goes: they pass to its longest-serving active
    owner (or other member). Opportunity.posted_by cascades on delete, so
    without this, deleting the person would delete the company's jobs and
    every application to them. No-op if nobody else is on the team."""
    from apps.opportunities.models import Opportunity

    others = company.memberships.exclude(user=user).select_related("user")
    heir = (others.filter(role=Role.OWNER, user__is_active=True).first()
            or others.filter(user__is_active=True).first()
            or others.first())
    if heir is not None:
        Opportunity.objects.filter(company=company, posted_by=user).update(posted_by=heir.user)


def keep_company_jobs(user) -> None:
    """Call before deleting a person: jobs they posted for any company
    (including ones they've left) pass to that company's team instead of
    cascading away. Must run *before* delete(); Django decides what a delete
    cascades to before any delete signal fires."""
    from apps.opportunities.models import Opportunity

    company_ids = (Opportunity.objects.filter(posted_by=user).exclude(company=None)
                   .values_list("company_id", flat=True).distinct())
    for company in Company.objects.filter(pk__in=list(company_ids)):
        reassign_company_jobs(user, company)


def ensure_active_owner(company: Company, departing_user=None) -> CompanyMembership | None:
    """If no active owner is left (other than `departing_user`), promote an
    active admin, else the longest-serving active member. Returns whoever was
    promoted."""
    company = _lock_company(company)
    others = company.memberships.select_related("user").filter(user__is_active=True)
    if departing_user is not None:
        others = others.exclude(user=departing_user)
    if not others.exists() or others.filter(role=Role.OWNER).exists():
        return None
    successor = others.filter(role=Role.ADMIN).first() or others.first()
    successor.role = Role.OWNER
    successor.save(update_fields=["role"])
    return successor


def invite_member(company: Company, inviter: CompanyMembership, email: str, role: str) -> tuple:
    """Owners invite anyone; admins invite admins and recruiters. Re-inviting
    the same email replaces the earlier invitation (a fresh link)."""
    if not inviter.can_manage:
        raise PermissionDenied("Only owners and admins can invite people.")
    if role == Role.OWNER and inviter.role != Role.OWNER:
        raise PermissionDenied("Only an owner can invite another owner.")
    email = email.strip()
    if company.memberships.filter(user__email__iexact=email).exists():
        raise ValidationError({"email": "This person is already on your team."})
    if company.invitations.filter(accepted_at=None, expires_at__gt=timezone.now()).count() >= 50:
        raise ValidationError({"email": "You have too many open invitations. Revoke some first."})
    company.invitations.filter(email__iexact=email, accepted_at=None).delete()
    invitation, token = CompanyInvitation.issue(company, email, role, inviter.user)
    notifications.team_invitation(invitation, token)
    return invitation, token


def revoke_invitation(invitation: CompanyInvitation, actor: CompanyMembership) -> None:
    if not actor.can_manage:
        raise PermissionDenied("Only owners and admins can manage invitations.")
    if invitation.role == Role.OWNER and actor.role != Role.OWNER:
        raise PermissionDenied("Only an owner can revoke an owner invitation.")
    invitation.delete()


@transaction.atomic
def accept_invitation(invitation: CompanyInvitation, user) -> CompanyMembership:
    """The invited person joins. They must be signed in with the address the
    invitation was sent to, so a forwarded link can't be used by someone else."""
    invitation = CompanyInvitation.objects.select_for_update().get(pk=invitation.pk)
    if not invitation.is_pending:
        raise ValidationError({"detail": "This invitation has expired or was already used. Ask for a new one."})
    if user.email.lower() != invitation.email.lower():
        raise PermissionDenied(
            f"This invitation was sent to {invitation.email}. Sign in with that address to accept it."
        )
    def already_on_a_team(existing):
        if existing is not None and existing.company_id == invitation.company_id:
            return ValidationError({"detail": "You're already on this team."})
        name = existing.company.name if existing is not None else "a company"
        return ValidationError({"detail": f"You're already on {name}'s team. Leave it before joining another company."})

    existing = CompanyMembership.for_user(user)
    if existing is not None:
        raise already_on_a_team(existing)
    try:
        with transaction.atomic():  # two invitations accepted at once: one wins
            membership = CompanyMembership.objects.create(
                company=invitation.company, user=user, role=invitation.role, invited_by=invitation.invited_by,
            )
    except IntegrityError:
        raise already_on_a_team(CompanyMembership.for_user(user))
    invitation.accepted_at = timezone.now()
    invitation.accepted_by = user
    invitation.save(update_fields=["accepted_at", "accepted_by"])
    return membership


@transaction.atomic
def change_role(target: CompanyMembership, actor: CompanyMembership, role: str) -> CompanyMembership:
    """Only owners change roles, and a company always keeps an owner."""
    if actor.role != Role.OWNER:
        raise PermissionDenied("Only an owner can change roles.")
    if role not in Role.values:
        raise ValidationError({"role": "Choose owner, admin or recruiter."})
    _lock_company(target.company)
    target = CompanyMembership.objects.select_related("user").get(pk=target.pk)
    if (target.role == Role.OWNER and role != Role.OWNER and target.user.is_active
            and _active_owner_count(target.company) <= 1):
        raise ValidationError({"role": "A company needs at least one owner. Make someone else an owner first."})
    target.role = role
    target.save(update_fields=["role"])
    return target


@transaction.atomic
def remove_member(target: CompanyMembership, actor: CompanyMembership) -> None:
    """Owners remove anyone, admins remove recruiters, and anyone can leave.
    The last owner can't leave or be removed. Jobs they posted stay with the
    company."""
    leaving = target.pk == actor.pk
    if not leaving:
        if actor.role == Role.ADMIN and target.role != Role.RECRUITER:
            raise PermissionDenied("Admins can only remove recruiters.")
        if actor.role == Role.RECRUITER:
            raise PermissionDenied("Only owners and admins can remove people.")
    _lock_company(target.company)
    target = CompanyMembership.objects.select_related("user", "company").get(pk=target.pk)
    if target.role == Role.OWNER and target.user.is_active and _active_owner_count(target.company) <= 1:
        raise ValidationError({"detail": "A company needs at least one owner. Make someone else an owner first."})
    # Their jobs stay with the company, and they lose access to its unpublished ones.
    reassign_company_jobs(target.user, target.company)
    target.delete()


# Identity fields a moderator checked when approving (and, for the badge,
# verified). Once approved they can only be changed by our team, so an
# approved or verified company can't turn into someone else.
LOCKED_AFTER_APPROVAL = ("name", "website")


def update_company(company: Company, data) -> Company:
    """A rejected company that edits its profile goes back into the queue."""
    if company.status in (Company.Status.APPROVED, Company.Status.SUSPENDED):
        changed = [f for f in LOCKED_AFTER_APPROVAL if f in data and data[f] != getattr(company, f)]
        if changed:
            raise ValidationError({
                f: "This was checked when your company was approved. Contact us to change it." for f in changed
            })
    for field, value in data.items():
        setattr(company, field, value)
    if company.status == Company.Status.REJECTED:
        company.status = Company.Status.PENDING
        company.rejection_reason = ""
    company.save()
    return company


def review_company(company: Company, reviewer, action: str, reason: str = "") -> Company:
    """approve | verify | unverify | reject | suspend, then tell the company."""
    if action == "approve":
        company.approve(reviewer)
    elif action == "verify":
        company.set_verified(reviewer, True)
    elif action == "unverify":
        company.set_verified(reviewer, False)
        return company  # no email for losing the badge alone; posting continues as normal
    elif action == "reject":
        company.reject(reviewer, reason or "Your company profile could not be verified.")
    elif action == "suspend":
        company.suspend(reviewer, reason)
    else:
        raise ValueError(action)
    notifications.company_reviewed(company)
    if action in ("reject", "suspend"):
        from config.seo import request_site_rebuild
        request_site_rebuild(f"company {company.pk} {action}ed")
    return company


# --- Jobs -------------------------------------------------------------------

def _check_method(data, requirements, instance=None):
    method = data.get("application_method", instance.application_method if instance else "external")
    url = data.get("opportunity_url", instance.opportunity_url if instance else "")
    if method == Opportunity.ApplicationMethod.EXTERNAL and not url:
        raise ValidationError({"opportunity_url": "Add the link where people apply, or choose in-app applications."})
    if method == Opportunity.ApplicationMethod.EXTERNAL and requirements:
        raise ValidationError({"requirements": "Requirements only apply to in-app applications."})


def _publish_or_hold(job, company, requirements):
    """Verified companies publish directly, unless a requirement needs a human look."""
    terms = flagged_terms(requirements)
    if company.publishes_directly and not terms:
        job.approve(reviewer=None)  # no human reviewer: the badge is the approval
    elif terms:
        notifications.job_held_for_review(job, terms)


@transaction.atomic
def post_job(company: Company, user, data, requirements) -> Opportunity:
    """An approved company posts a job. Verified companies publish straight
    away; the rest go through the normal moderation queue."""
    if not company.can_post:
        raise PermissionDenied("Your company must be approved before it can post jobs.")
    _check_method(data, requirements)

    opportunity = Opportunity.objects.create(
        posted_by=user,
        company=company,
        organization=company.name,
        source_type=Opportunity.SourceType.COMPANY,
        status=Opportunity.Status.PENDING,
        **data,
    )
    ApplicationRequirement.objects.bulk_create([
        ApplicationRequirement(opportunity=opportunity, position=i, **req) for i, req in enumerate(requirements)
    ])
    _publish_or_hold(opportunity, company, requirements)
    return opportunity


@transaction.atomic
def update_job(job: Opportunity, company: Company, data, requirements=None) -> Opportunity:
    """Edit a posted job. An unverified company's edit goes back to review
    (an approved listing must not change unseen). Requirements can't change
    once anyone has applied, so every applicant answered the same questions."""
    if not company.can_post:
        raise PermissionDenied("Your company must be approved before it can edit jobs.")
    has_applicants = job.applications.exists()
    if has_applicants and "application_method" in data and data["application_method"] != job.application_method:
        raise ValidationError({"application_method": "People have already applied, so this can't change."})
    if requirements is not None and has_applicants:
        raise ValidationError({"requirements": "People have already applied, so the requirements are locked."})
    _check_method(data, requirements if requirements is not None else [], instance=job)

    for field, value in data.items():
        setattr(job, field, value)
    job.organization = company.name
    if requirements is not None:
        job.requirements.all().delete()
        ApplicationRequirement.objects.bulk_create([
            ApplicationRequirement(opportunity=job, position=i, **req) for i, req in enumerate(requirements)
        ])
    if job.application_method == Opportunity.ApplicationMethod.EXTERNAL:
        job.requirements.all().delete()

    # Back to the queue, then publish again only where a new post would be.
    # An edit must not re-date a live job (it would jump back to the top of
    # the feed and restart the early-access window), so keep its timestamps.
    was_live = job.status == Opportunity.Status.APPROVED
    published_at = job.published_at
    job.status = Opportunity.Status.PENDING
    job.rejection_reason = ""
    job.save()
    _publish_or_hold(job, company, list(job.requirements.values("label", "help_text")))
    if was_live and job.status == Opportunity.Status.APPROVED and published_at:
        job.published_at = published_at
        job.save(update_fields=["published_at"])
    return job


# --- Applications ------------------------------------------------------------

def _clean_answer(req: ApplicationRequirement, raw, upload):
    kind = req.kind
    if kind == ApplicationRequirement.Kind.FILE:
        if not upload:
            return None
        # Real type from the bytes, PDF/JPG/PNG only, scripts refused,
        # images re-encoded, virus-scanned (apps/documents/uploads.py).
        return clean_upload_or_400(upload, f"answer_{req.pk}")

    value = (raw or "").strip()
    if not value:
        return None
    if kind == ApplicationRequirement.Kind.SHORT_TEXT and len(value) > 500:
        raise ValidationError({f"answer_{req.pk}": "Keep this under 500 characters."})
    if kind == ApplicationRequirement.Kind.LONG_TEXT and len(value) > 10000:
        raise ValidationError({f"answer_{req.pk}": "Keep this under 10,000 characters."})
    if kind == ApplicationRequirement.Kind.URL and not value.lower().startswith(("http://", "https://")):
        raise ValidationError({f"answer_{req.pk}": "Enter a full link starting with https://"})
    if kind == ApplicationRequirement.Kind.YES_NO and value.lower() not in YES_NO:
        raise ValidationError({f"answer_{req.pk}": "Answer yes or no."})
    if kind == ApplicationRequirement.Kind.CHOICE and value not in (req.options or []):
        raise ValidationError({f"answer_{req.pk}": "Pick one of the listed options."})
    return value.lower() if kind == ApplicationRequirement.Kind.YES_NO else value


def _truthy(value) -> bool:
    return str(value).lower() in {"true", "1", "yes", "on"}


@transaction.atomic
def submit_application(user, opportunity: Opportunity, data, files) -> Application:
    """`data`/`files` carry one `answer_<requirement id>` entry per requirement,
    plus `consent`: the applicant's agreement to share them with the company."""
    if opportunity.application_method != Opportunity.ApplicationMethod.IN_APP:
        raise ValidationError({"detail": "This job takes applications on the company's own site."})
    if not opportunity.is_visible_to(user) or not opportunity.is_open:
        raise ValidationError({"detail": "This job isn't accepting applications."})
    if opportunity.company_id and CompanyMembership.objects.filter(company_id=opportunity.company_id, user=user).exists():
        raise ValidationError({"detail": "You can't apply to your own company's job."})
    if Application.objects.filter(opportunity=opportunity, applicant=user).exists():
        raise ValidationError({"detail": "You've already applied to this job."})
    if not _truthy(data.get("consent")):
        raise ValidationError({"consent": "Please agree to share your application with the company."})

    answers, missing = [], {}
    for req in opportunity.requirements.all():
        key = f"answer_{req.pk}"
        cleaned = _clean_answer(req, data.get(key), files.get(key))
        if cleaned is None:
            if req.required:
                missing[key] = "This is required."
            continue
        answers.append((req, cleaned))
    if missing:
        raise ValidationError(missing)

    try:
        with transaction.atomic():  # a double-click can race past the exists() check above
            application = Application.objects.create(opportunity=opportunity, applicant=user, consent_at=timezone.now())
    except IntegrityError:
        raise ValidationError({"detail": "You've already applied to this job."})
    for req, cleaned in answers:
        answer = ApplicationAnswer(application=application, requirement=req, label=req.label, kind=req.kind)
        if req.kind == ApplicationRequirement.Kind.FILE:
            answer.original_filename = cleaned.original_name
            answer.file.save(cleaned.file.name, cleaned.file, save=False)
        else:
            answer.value = cleaned
        answer.save()
    notifications.application_received(application)
    return application


def set_application_status(application: Application, data) -> Application:
    old = application.status
    for field, value in data.items():
        setattr(application, field, value)
    application.save()
    if application.status != old:
        notifications.application_status_changed(application)
    return application


def withdraw_application(application: Application) -> Application:
    """Withdrawing hides the application from the company and deletes every
    answer and uploaded file straight away (data minimisation). Only the
    bare record that an application was made and withdrawn remains."""
    application.status = Application.Status.WITHDRAWN
    application.company_note = ""
    application.save(update_fields=["status", "company_note", "updated_at"])
    application.answers.all().delete()  # signals.py removes the stored files
    return application
