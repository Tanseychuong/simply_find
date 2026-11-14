"""
Custom User model for the EEL opportunity portal.

Uses Django's AbstractBaseUser + PermissionsMixin rather than extending the
default User, so email is the login field (no separate username) and we
keep full control over what fields exist — same reasoning as the Flask
User model, just Django's idioms.

Moderator privilege is deliberately NOT a field here — it's a Django
permission (opportunities.can_verify_opportunity) granted via a
"Moderators" Group, assignable from the Django admin's Groups UI with no
custom code. See apps/opportunities/models.py's Meta.permissions.
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, name, password=None, **extra_fields):
        if not email:
            raise ValueError("Users must have an email address")
        email = self.normalize_email(email)
        user = self.model(email=email, name=name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, name, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, name, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    name = models.CharField(max_length=120)
    email = models.EmailField(unique=True)
    profile_picture = models.ImageField(upload_to="profile_pics/", null=True, blank=True)

    # is_staff/is_superuser come from PermissionsMixin and control Django
    # admin access + full permissions — is_staff is what makes someone able
    # to log into /admin/ at all (moderators need this; is_superuser is the
    # "admin" tier from the original plan).
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    # Set when the user asks to delete their account: they're deactivated
    # at once and permanently deleted after the hold (apps/accounts/deletion.py).
    deletion_requested_at = models.DateTimeField(null=True, blank=True)
    # Sign-in tokens issued before this moment are refused (set on password
    # reset, so a reset ends every other session). apps/accounts/authentication.py
    tokens_valid_after = models.DateTimeField(null=True, blank=True)
    # Google's stable account id ("sub"), set once the user signs in with
    # Google. Matched before email, so a changed Gmail address still works.
    google_sub = models.CharField(max_length=255, unique=True, null=True, blank=True, editable=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    def __str__(self):
        return self.email

    def token_is_current(self, issued_at) -> bool:
        """Was a token issued at `issued_at` (unix seconds) after the last cut-off?
        Whole seconds, matching the token's own `iat` precision."""
        if self.tokens_valid_after is None:
            return True
        return issued_at is not None and int(issued_at) >= int(self.tokens_valid_after.timestamp())

    def is_moderator(self) -> bool:
        """True for superusers too, so admins never need the explicit
        permission on top of is_superuser."""
        return self.is_superuser or self.has_perm("opportunities.can_verify_opportunity")
