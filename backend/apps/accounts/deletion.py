"""
Self-service account deletion, exactly as the Privacy notice (section 13)
describes it:

  1. the user asks (signed in, re-entering their password);
  2. the account is deactivated at once, so nobody can sign in with it;
  3. it is held for DELETION_HOLD so a mistaken or malicious request can be
     undone (an admin restores it from the Users admin);
  4. `manage.py purge_deleted_accounts` then deletes it permanently, with
     everything that cascades from it (posted listings, saved listings,
     applications and their files), and emails the person that it's done.

Company accounts belong to their team, not to one person:
  * the person's company, if they are its only member, is suspended at once
    and deleted with its jobs when the account is purged;
  * if others are on the team, the company stays. When the person was its
    only owner, another member becomes owner straight away (admins first,
    then the longest-serving member). Jobs they posted pass to an owner
    instead of being deleted with their account.

Keep DELETION_HOLD in sync with DELETION_HOLD in
frontend/src/routes/public/Privacy.jsx.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

DELETION_HOLD = timedelta(days=14)


def _email(subject, body, to):
    try:
        send_mail(subject, body + f"\n\nSimplyFind\n{settings.SITE_URL}",
                  settings.DEFAULT_FROM_EMAIL, [to])
    except Exception:  # noqa: BLE001 - an email failure must not undo or block the deletion
        logger.exception("Could not send account-deletion email")


@transaction.atomic
def request_deletion(user):
    if user.is_superuser:
        raise PermissionDenied("Administrators can't delete their own account here. Ask another administrator.")
    user.is_active = False
    user.deletion_requested_at = timezone.now()
    user.save(update_fields=["is_active", "deletion_requested_at"])

    _hand_over_company(user)

    days = DELETION_HOLD.days
    email, name = user.email, user.name
    transaction.on_commit(lambda: _email(
        "We've received your request to delete your account",
        f"Hi {name},\n\nYour SimplyFind account has been deactivated and will be permanently deleted "
        f"in {days} days, together with the opportunities you posted, your saved listings and your job "
        "applications.\n\nIf you didn't ask for this, or you've changed your mind, reply to this email within "
        f"{days} days and we'll restore your account.",
        email,
    ))
    return user


def _hand_over_company(user):
    from apps.companies import notifications
    from apps.companies.models import CompanyMembership
    from apps.companies.services import ensure_active_owner

    membership = CompanyMembership.for_user(user)
    if membership is None:
        return
    company = membership.company
    if not company.memberships.exclude(user=user).filter(user__is_active=True).exists():
        # A company nobody can sign in to must not keep taking applications.
        if company.status == company.Status.APPROVED:
            company.suspend(reviewer=None, reason="Its only team member asked to delete their account.")
        return
    # Whoever is leaving (owner or not), the company must keep an owner who
    # can still sign in.
    successor = ensure_active_owner(company, departing_user=user)
    if successor is not None:
        notifications.promoted_to_owner(successor, user.name)


def _release_company(user):
    """Just before purging: delete a company only this person was on (with
    its jobs). Otherwise the jobs they posted pass to the team, which also
    happens for any company they *used to* be on."""
    from apps.companies.models import CompanyMembership
    from apps.companies.services import keep_company_jobs
    from apps.opportunities.models import Opportunity

    membership = CompanyMembership.for_user(user)
    if membership is not None and not membership.company.memberships.exclude(user=user).exists():
        company = membership.company
        Opportunity.objects.filter(company=company).delete()
        company.delete()
    keep_company_jobs(user)


def restore(user):
    """Undo a deletion request during the hold (admin action)."""
    user.is_active = True
    user.deletion_requested_at = None
    user.save(update_fields=["is_active", "deletion_requested_at"])
    return user


def due_for_deletion(now=None):
    from .models import User

    cutoff = (now or timezone.now()) - DELETION_HOLD
    return User.objects.filter(is_active=False, deletion_requested_at__isnull=False, deletion_requested_at__lte=cutoff)


def purge_due_accounts(now=None) -> int:
    count = 0
    for user in due_for_deletion(now).iterator():
        email, name = user.email, user.name
        with transaction.atomic():
            _release_company(user)
            user.delete()
        count += 1
        _email(
            "Your account has been deleted",
            f"Hi {name},\n\nAs you asked, your SimplyFind account and the information linked to it "
            "have now been permanently deleted. If you'd like to come back, you're welcome to register again.",
            email,
        )
    return count
