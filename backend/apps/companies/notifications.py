"""
Transactional emails for company accounts and applications.

Rules (privacy and deliverability):
  * Only service messages about something the recipient did or is party to,
    never marketing.
  * Never put an applicant's answers or files in an email. The company is
    told *that* someone applied and reads the application in its dashboard.
  * Sent after the database commit, and a failed send never breaks the
    request (it is logged instead).
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

logger = logging.getLogger(__name__)

SIGN_OFF = "\n\nGlobal Opportunities\n{site}"


def _send(subject, body, recipients):
    recipients = [r for r in recipients if r]
    if not recipients:
        return

    def deliver():
        try:
            send_mail(
                subject=subject,
                message=body + SIGN_OFF.format(site=settings.SITE_URL),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
            )
        except Exception:  # noqa: BLE001 - email must never break the action that triggered it
            logger.exception("Could not send email %r", subject)

    transaction.on_commit(deliver)


def _company_recipients(company):
    return company.notification_emails()


def team_invitation(invitation, token):
    """The only copy of the invitation link goes to the invited address."""
    company = invitation.company
    inviter = invitation.invited_by.name if invitation.invited_by else "Someone"
    days = invitation.VALID_FOR.days
    _send(
        f"{inviter} invited you to {company.name} on Global Opportunities",
        f"Hi,\n\n{inviter} invited you to join {company.name}'s hiring team on Global Opportunities "
        f"as {invitation.get_role_display().lower()}.\n\n"
        f"Accept the invitation (the link works for {days} days, once):\n"
        f"{settings.SITE_URL}/companies/invite/{token}\n\n"
        f"Sign in or create an account with this email address ({invitation.email}) to accept. "
        "If you weren't expecting this, you can ignore it.",
        [invitation.email],
    )


def promoted_to_owner(membership, departing_name):
    company = membership.company
    _send(
        f"You're now an owner of {company.name} on Global Opportunities",
        f"Hi {membership.user.name},\n\n{departing_name} asked to delete their account, and they were the only "
        f"owner of {company.name}. So that the company isn't left without one, you're now an owner: you can "
        f"manage the team, its roles and the company profile.\n\nDashboard: {settings.SITE_URL}/company",
        [membership.user.email],
    )


def company_reviewed(company):
    """Approved, verified, rejected or suspended."""
    status = company.status
    if status == "approved" and company.is_verified:
        subject = f"{company.name} is now verified on Global Opportunities"
        body = (f"Good news: {company.name} has the verified badge. Jobs you post now go live straight away, "
                "unless a requirement needs a closer look by our team.")
    elif status == "approved":
        subject = f"{company.name} is approved on Global Opportunities"
        body = (f"Your company profile for {company.name} is approved, so you can now post jobs from your dashboard. "
                "Each job is checked by a moderator before it goes live.")
    elif status == "rejected":
        subject = f"Your company profile for {company.name} wasn't approved"
        body = (f"We couldn't approve the company profile for {company.name}."
                + (f"\n\nReason: {company.rejection_reason}" if company.rejection_reason else "")
                + "\n\nYou can update your profile in the dashboard to send it for review again.")
    elif status == "suspended":
        subject = f"{company.name}'s account is suspended"
        body = (f"Posting for {company.name} is paused and its jobs are hidden from the site."
                + (f"\n\nReason: {company.rejection_reason}" if company.rejection_reason else "")
                + "\n\nReply to this email if you think this is a mistake.")
    else:
        return
    _send(subject, f"Hi,\n\n{body}\n\nDashboard: {settings.SITE_URL}/company", _company_recipients(company))


def application_received(application):
    job = application.opportunity
    company = job.company
    if company is None:
        return
    # To the company: no answers, no files, only that someone applied.
    _send(
        f"New application: {job.title}",
        f"Hi,\n\n{application.applicant.name} applied for {job.title}.\n\n"
        f"Read the application in your dashboard: {settings.SITE_URL}/company",
        _company_recipients(company),
    )
    # To the applicant: a receipt.
    _send(
        f"Application sent: {job.title} at {company.name}",
        f"Hi {application.applicant.name},\n\nYour application for {job.title} at {company.name} was sent. "
        f"{company.name} now has your name, email address and answers.\n\n"
        f"Track or withdraw it here: {settings.SITE_URL}/applications",
        [application.applicant.email],
    )


STATUS_MESSAGES = {
    "reviewing": "is being reviewed",
    "shortlisted": "has been shortlisted",
    "rejected": "was not selected this time",
    "hired": "was successful. Congratulations!",
}


def application_status_changed(application):
    phrase = STATUS_MESSAGES.get(application.status)
    if not phrase:
        return
    job = application.opportunity
    company_name = job.company.name if job.company_id else job.organization
    _send(
        f"Update on your application: {job.title}",
        f"Hi {application.applicant.name},\n\nYour application for {job.title} at {company_name} {phrase}.\n\n"
        f"See all your applications: {settings.SITE_URL}/applications",
        [application.applicant.email],
    )


def job_held_for_review(job, terms):
    _send(
        f"Your job '{job.title}' is waiting for a quick review",
        "Hi,\n\nYour job was received. Because some application questions ask about personal characteristics "
        f"({', '.join(terms)}), a moderator will check it before it goes live. Asking about things like age, "
        "religion, ethnicity or marital status can be unlawful in many countries; consider removing them.\n\n"
        f"Dashboard: {settings.SITE_URL}/company",
        _company_recipients(job.company),
    )
