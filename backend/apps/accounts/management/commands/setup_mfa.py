"""
Run via: python manage.py setup_mfa <email>

Starts two-step sign-in for an account from the server shell, for the first
admin (who can't reach the admin without it). Prints the secret and the
otpauth:// link to add to an authenticator app, then asks for a code to
confirm and prints the recovery codes.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.accounts import mfa
from apps.accounts.models import User


class Command(BaseCommand):
    help = "Set up two-step sign-in (TOTP) for an account"

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--code", help="A current code, to confirm without a prompt")

    def handle(self, *args, email, code=None, **options):
        user = User.objects.filter(email__iexact=email).first()
        if user is None:
            raise CommandError(f"No account for {email}.")
        if user.mfa_enabled:
            raise CommandError("Two-step sign-in is already on for this account.")
        setup = mfa.start_setup(user)
        self.stdout.write(f"Secret: {setup['secret']}\nAdd to your app: {setup['otpauth_uri']}")
        code = code or input("Enter the six-digit code your app shows: ")
        codes = mfa.enable(user, code)
        if codes is None:
            raise CommandError("That code isn't right. Run the command again.")
        self.stdout.write(self.style.SUCCESS("Two-step sign-in is on. Recovery codes (keep them safe):"))
        for recovery in codes:
            self.stdout.write(f"  {recovery}")
