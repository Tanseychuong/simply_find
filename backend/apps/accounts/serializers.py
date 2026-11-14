from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Read-only representation used by /me and anywhere else a user's
    public info is embedded (e.g. Opportunity.posted_by)."""

    is_premium_active = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    company = serializers.SerializerMethodField()
    # How the user signs in, so the profile can offer the right confirmation
    # (password vs Google) for sensitive actions such as deleting the account.
    has_password = serializers.SerializerMethodField()
    google_linked = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "name", "email", "profile_picture", "is_premium_active", "role", "company",
                  "has_password", "google_linked", "created_at"]
        read_only_fields = fields

    def get_has_password(self, obj) -> bool:
        return obj.has_usable_password()

    def get_google_linked(self, obj) -> bool:
        return bool(obj.google_sub)

    def get_is_premium_active(self, obj) -> bool:
        # Frozen premium: nobody is shown as Premium, whatever the flag says.
        return settings.PREMIUM_ENABLED and obj.is_premium_active()

    def get_company(self, obj):
        """The company account this user is on the team of, and their role."""
        from apps.companies.models import CompanyMembership

        membership = CompanyMembership.for_user(obj)
        if membership is None:
            return None
        company = membership.company
        return {"id": company.id, "name": company.name, "slug": company.slug, "logo_url": company.logo_url,
                "status": company.status, "is_verified": company.is_verified, "role": membership.role}

    def get_role(self, obj) -> str:
        if obj.is_superuser:
            return "admin"
        if obj.is_moderator():
            return "moderator"
        return "user"


class UserUpdateSerializer(serializers.ModelSerializer):
    """Write serializer for a user editing their own profile — deliberately
    excludes email, password, role/premium fields. Those go through their
    own dedicated flows (email is the login identity, password has its own
    change flow, role/premium are admin-only)."""

    class Meta:
        model = User
        fields = ["name", "profile_picture"]

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Name cannot be blank.")
        return value.strip()

    def validate_profile_picture(self, value):
        # Every upload lands in paid cloud storage — keep them reasonable.
        if value and value.size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise serializers.ValidationError(f"Image must be {settings.MAX_UPLOAD_MB} MB or smaller.")
        return value


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["name", "email", "password"]

    def validate_email(self, value):
        # The database only enforces exact-case uniqueness; Ama@ and ama@ are
        # the same mailbox and must not become two accounts.
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("user with this email already exists.")
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Checks the uid/token pair from the reset link and the new password.
    On success, ``validated_data["user"]`` is the account to update."""

    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True)

    default_error_messages = {
        "invalid_link": "This reset link is invalid or has expired. Please request a new one.",
    }

    def validate(self, attrs):
        try:
            pk = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=pk, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"detail": self.error_messages["invalid_link"]})

        try:
            validate_password(attrs["password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        attrs["user"] = user
        return attrs
