from django.utils import timezone
from rest_framework import serializers

from apps.documents.models import Credential, Document, DocumentAccess
from apps.opportunities.models import OpportunityCategory

from .models import StudentProfile
from .steps import progress


def _clean_list(values, *, limit, max_len, what):
    seen, cleaned = set(), []
    for value in values:
        value = " ".join(str(value).split())
        if not value or value.lower() in seen:
            continue
        if len(value) > max_len:
            raise serializers.ValidationError(f"Keep each {what} under {max_len} characters.")
        seen.add(value.lower())
        cleaned.append(value)
    if len(cleaned) > limit:
        raise serializers.ValidationError(f"Add up to {limit} {what}s.")
    return cleaned


class StudentProfileSerializer(serializers.ModelSerializer):
    """The owner's own profile. `name` is the account name, edited here so
    step 1 is one form."""

    name = serializers.CharField(source="user.name", max_length=120, required=False)
    field = serializers.SlugRelatedField(
        slug_field="slug", queryset=OpportunityCategory.objects.all(), required=False, allow_null=True,
    )
    skills = serializers.ListField(child=serializers.CharField(), required=False)
    languages = serializers.ListField(child=serializers.CharField(), required=False)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = StudentProfile
        fields = [
            "name", "date_of_birth", "phone", "country", "city",
            "status", "institution", "programme", "field", "graduation_year",
            "headline", "skills", "languages", "progress", "updated_at",
        ]
        read_only_fields = ["progress", "updated_at"]

    def get_progress(self, profile):
        return progress(profile)

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Enter your name.")
        return value.strip()

    def validate_date_of_birth(self, value):
        if value is None:
            return value
        today = timezone.localdate()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 14 or age > 80:
            raise serializers.ValidationError("Check your date of birth.")
        return value

    def validate_graduation_year(self, value):
        if value is None:
            return value
        year = timezone.localdate().year
        if not year - 60 <= value <= year + 8:
            raise serializers.ValidationError("Check the graduation year.")
        return value

    def validate_phone(self, value):
        value = value.strip()
        digits = "".join(c for c in value if c.isdigit())
        if value and (len(digits) < 7 or any(c not in "0123456789+ -()" for c in value)):
            raise serializers.ValidationError("Enter a phone number with its country code, like +211 912 345 678.")
        return value

    def validate_skills(self, value):
        return _clean_list(value, limit=StudentProfile.MAX_SKILLS, max_len=40, what="skill")

    def validate_languages(self, value):
        return _clean_list(value, limit=10, max_len=40, what="language")

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        if "name" in user_data:
            instance.user.name = user_data["name"]
            instance.user.save(update_fields=["name"])
        return super().update(instance, validated_data)


class ApplicantProfileSerializer(serializers.ModelSerializer):
    """What a hiring company sees: studies and skills, never date of birth."""

    field = serializers.CharField(source="field.name", default=None)

    class Meta:
        model = StudentProfile
        fields = ["status", "institution", "programme", "field", "graduation_year", "headline", "skills", "languages",
                  "country", "city"]
        read_only_fields = fields


class DocumentSerializer(serializers.ModelSerializer):
    uploaded_by_someone_else = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = ["id", "kind", "title", "original_filename", "content_type", "size", "created_at",
                  "uploaded_by_someone_else", "consent_at"]
        read_only_fields = ["id", "original_filename", "content_type", "size", "created_at",
                            "uploaded_by_someone_else", "consent_at"]

    def get_uploaded_by_someone_else(self, document):
        return document.uploaded_by_id is not None


class CredentialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Credential
        fields = ["id", "provider", "title", "issuer", "url", "issued_on", "check_status", "check_detail",
                  "checked_at", "created_at"]
        read_only_fields = ["id", "check_status", "check_detail", "checked_at", "created_at"]
        extra_kwargs = {"provider": {"required": False}, "title": {"required": False}}

    def validate_url(self, value):
        if not value.lower().startswith("https://"):
            raise serializers.ValidationError("Use the certificate's full https:// link.")
        return value

    def validate(self, attrs):
        if attrs.get("provider") != Credential.Provider.OPEN_BADGE and not attrs.get("title", "").strip():
            raise serializers.ValidationError({"title": "What is the certificate called?"})
        return attrs


class DocumentAccessSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocumentAccess
        fields = ["id", "viewer_name", "company_name", "label", "accessed_at"]
        read_only_fields = fields
