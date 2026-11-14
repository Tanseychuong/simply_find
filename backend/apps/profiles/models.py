"""
A student's or recent graduate's profile, filled in four short steps
(steps.py) so it can be done on a phone in a few minutes.

Date of birth is only used to check age rules (eligibility.py). Companies
never see it, only the owner and moderators.
"""

from django.conf import settings
from django.db import models


class StudentProfile(models.Model):
    class Status(models.TextChoices):
        STUDENT = "student", "Student"
        GRADUATE = "graduate", "Recent graduate"

    MAX_SKILLS = 20

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile")

    # Step 1: about you
    date_of_birth = models.DateField(null=True, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    country = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=80, blank=True)

    # Step 2: studies
    status = models.CharField(max_length=10, choices=Status.choices, blank=True)
    institution = models.CharField(max_length=200, blank=True)
    programme = models.CharField(max_length=200, blank=True)
    field = models.ForeignKey(
        "opportunities.OpportunityCategory", on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    # Expected year for students, the year they finished for graduates.
    graduation_year = models.PositiveSmallIntegerField(null=True, blank=True)

    # Step 3: skills
    headline = models.CharField(max_length=160, blank=True)
    skills = models.JSONField(default=list, blank=True)
    languages = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user}"

    @classmethod
    def for_user(cls, user) -> "StudentProfile":
        profile, _ = cls.objects.get_or_create(user=user)
        return profile

    def age_on(self, day) -> int | None:
        dob = self.date_of_birth
        if dob is None:
            return None
        return day.year - dob.year - ((day.month, day.day) < (dob.month, dob.day))
