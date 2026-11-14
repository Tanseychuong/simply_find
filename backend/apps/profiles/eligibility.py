"""
Who can apply for a role. SimplyFind is for students and recent graduates:
  * a graduate can apply up to RECENT_GRADUATE_YEARS after graduating;
  * a role may ask for a graduation-year range;
  * under-18s can apply only where the company says it accepts minors.
"""

from django.conf import settings
from django.utils import timezone

from .models import StudentProfile
from .steps import ready_to_apply


def reasons_not_eligible(user, opportunity) -> list[str]:
    profile = StudentProfile.objects.filter(user=user).first() or StudentProfile(user=user)
    missing = ready_to_apply(profile)
    if missing:
        return ["Finish your profile first: add " + ", ".join(missing) + "."]

    reasons = []
    today = timezone.localdate()
    year = profile.graduation_year
    if profile.status == StudentProfile.Status.GRADUATE and year > today.year:
        reasons.append("Your graduation year is in the future: choose 'Student' if you're still studying.")
    elif today.year - year > settings.RECENT_GRADUATE_YEARS:
        reasons.append(
            f"SimplyFind roles are for students and people who graduated in the last "
            f"{settings.RECENT_GRADUATE_YEARS} years."
        )
    if opportunity.graduation_year_min and year < opportunity.graduation_year_min:
        reasons.append(f"This role is for people graduating in {opportunity.graduation_year_min} or later.")
    if opportunity.graduation_year_max and year > opportunity.graduation_year_max:
        reasons.append(f"This role is for people graduating by {opportunity.graduation_year_max}.")
    age = profile.age_on(today)
    if age is not None and age < 18 and not opportunity.accepts_minors:
        reasons.append("This role is open to people aged 18 or over.")
    return reasons
