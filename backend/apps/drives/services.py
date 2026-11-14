import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.accounts.verification import mark_verified
from apps.documents.models import Document
from apps.documents.services import add_document
from apps.profiles.models import StudentProfile
from apps.profiles.serializers import StudentProfileSerializer

from .models import UNCLAIMED_DAYS, DriveRegistration, RecruitmentDrive

logger = logging.getLogger(__name__)

CLAIM_SALT = "simplyfind.claim-account"
DESK_UPLOAD_HOURS = 24


# --- Claim links ---------------------------------------------------------------

def claim_token(registration: DriveRegistration) -> str:
    # Tied to the password hash: once a password is set, the link stops working.
    student = registration.student
    return signing.dumps({"r": registration.pk, "u": student.pk, "p": student.password[-16:]}, salt=CLAIM_SALT)


def registration_for_token(token: str) -> DriveRegistration | None:
    try:
        data = signing.loads(token or "", salt=CLAIM_SALT, max_age=UNCLAIMED_DAYS * 24 * 3600)
    except signing.BadSignature:
        return None
    registration = (DriveRegistration.objects.select_related("student", "drive__company")
                    .filter(pk=data.get("r"), student_id=data.get("u"), claimed_at=None).first())
    if registration is None or registration.student.password[-16:] != data.get("p"):
        return None
    return registration


def send_claim_email(registration: DriveRegistration) -> None:
    student, drive = registration.student, registration.drive
    link = f"{settings.FRONTEND_URL.rstrip('/')}/claim?token={claim_token(registration)}"

    def _send():
        try:
            send_mail(
                subject=f"Finish your SimplyFind account from {drive.name}",
                message=(
                    f"Hi {student.name},\n\n"
                    f"The {drive.company.name} team signed you up for SimplyFind at {drive.name}"
                    + (f" ({drive.location})" if drive.location else "") + ".\n\n"
                    "Choose a password to claim your account and check the details and documents "
                    f"added for you (the link works for {UNCLAIMED_DAYS} days):\n\n{link}\n\n"
                    "Until you claim it, nobody can apply in your name. If you didn't ask for this, "
                    f"ignore this email: the account and its documents are deleted after {UNCLAIMED_DAYS} days.\n\n"
                    f"SimplyFind\n{settings.SITE_URL}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[student.email],
            )
        except Exception:  # noqa: BLE001 - email must never break the signup
            logger.exception("Could not send the claim email for registration %s", registration.pk)

    transaction.on_commit(_send)


# --- Signups ---------------------------------------------------------------------

PROFILE_FIELDS = ("date_of_birth", "phone", "country", "city", "status", "institution", "programme",
                  "field", "graduation_year")


@transaction.atomic
def assisted_signup(drive: RecruitmentDrive, assistant, data) -> DriveRegistration:
    if not str(data.get("consent", "")).lower() in ("true", "1", "yes", "on"):
        raise ValidationError({"consent": "Confirm the student agreed to be signed up and to their documents "
                                          "being scanned."})
    name = str(data.get("name") or "").strip()
    email = User.objects.normalize_email(str(data.get("email") or "").strip())
    if not name:
        raise ValidationError({"name": "Enter the student's name."})
    if "@" not in email:
        raise ValidationError({"email": "Enter the student's email address."})
    if User.objects.filter(email__iexact=email).exists():
        raise ValidationError({"email": "This email already has a SimplyFind account. Ask the student to sign "
                                        f"in and open the drive's link (code {drive.code})."})
    profile_data = {k: data[k] for k in PROFILE_FIELDS if k in data and data[k] not in ("", None)}
    serializer = StudentProfileSerializer(data=profile_data, partial=True)
    serializer.is_valid(raise_exception=True)

    student = User.objects.create_user(email=email, name=name[:120], password=None)  # no password until claimed
    profile = StudentProfile.for_user(student)
    serializer.update(profile, serializer.validated_data)
    registration = DriveRegistration.objects.create(
        drive=drive, student=student, method=DriveRegistration.Method.ASSISTED,
        registered_by=assistant, desk_consent_at=timezone.now(),
    )
    send_claim_email(registration)
    return registration


def desk_upload(registration: DriveRegistration, assistant, upload, kind, title) -> Document:
    """The team scans a student's document at the desk, before the student
    has claimed the account, and only on the day."""
    if registration.claimed_at or registration.method != DriveRegistration.Method.ASSISTED:
        raise ValidationError({"detail": "The student manages their own documents now."})
    if timezone.now() - registration.created_at > timedelta(hours=DESK_UPLOAD_HOURS):
        raise ValidationError({"detail": "Documents can only be added at the desk on the day of the signup."})
    return add_document(registration.student, upload, kind=kind, title=title, uploaded_by=assistant, consent=False)


def record_self_signup(drive_code: str, student) -> None:
    drive = RecruitmentDrive.objects.filter(code=(drive_code or "").strip().upper(), is_active=True).first()
    if drive:
        DriveRegistration.objects.get_or_create(
            drive=drive, student=student,
            defaults={"method": DriveRegistration.Method.SELF, "claimed_at": timezone.now()},
        )


@transaction.atomic
def claim(registration: DriveRegistration, password: str) -> User:
    student = registration.student
    try:
        validate_password(password, student)
    except DjangoValidationError as exc:
        raise ValidationError({"password": list(exc.messages)})
    student.set_password(password)
    student.save(update_fields=["password"])
    mark_verified(student)  # the claim link came to this mailbox
    now = timezone.now()
    registration.claimed_at = now
    registration.save(update_fields=["claimed_at"])
    Document.objects.filter(owner=student, consent_at=None).update(consent_at=now)
    return student


def purge_unclaimed(now=None) -> int:
    cutoff = (now or timezone.now()) - timedelta(days=UNCLAIMED_DAYS)
    stale = DriveRegistration.objects.filter(
        method=DriveRegistration.Method.ASSISTED, claimed_at=None, created_at__lt=cutoff,
        student__last_login=None,
    ).select_related("student")
    count = 0
    for registration in stale:
        if not registration.student.has_usable_password():
            registration.student.delete()  # documents and their files go with it
            count += 1
    return count
