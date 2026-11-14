from rest_framework import serializers

from apps.accounts.models import User

from .models import Opportunity, OpportunityCategory, SavedOpportunity
from .sections import KINDS, clean_sections, text_to_blocks


class PosterSerializer(serializers.ModelSerializer):
    """Who posted a listing, as anyone browsing may see it — no email,
    role or premium status (listings are public)."""

    class Meta:
        model = User
        fields = ["id", "name", "profile_picture"]
        read_only_fields = fields


class OpportunityCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = OpportunityCategory
        fields = ["id", "slug", "name", "description"]


class OpportunityCategoryWithCountSerializer(OpportunityCategorySerializer):
    """Used by GET /categories/ — `live_count` is annotated in the view
    with the same visibility rule as the feed."""

    live_count = serializers.IntegerField(read_only=True)

    class Meta(OpportunityCategorySerializer.Meta):
        fields = OpportunityCategorySerializer.Meta.fields + ["live_count"]


class OpportunitySerializer(serializers.ModelSerializer):
    """Read serializer — used for list/retrieve. Anything derived (is_saved,
    category/poster details) is computed here so the frontend doesn't need
    a second request per opportunity."""

    category = OpportunityCategorySerializer(read_only=True)
    posted_by = PosterSerializer(read_only=True)
    is_saved = serializers.SerializerMethodField()
    is_open = serializers.BooleanField(read_only=True)
    company = serializers.SerializerMethodField()

    class Meta:
        model = Opportunity
        fields = [
            "id", "title", "organization", "description", "location",
            "opportunity_url", "application_deadline", "image_url",
            "category", "posted_by", "source_type",
            "published_at", "source_published_at", "is_open", "is_saved",
            "company", "application_method",
        ]
        read_only_fields = fields

    def get_company(self, obj):
        if not obj.company_id:
            return None
        from apps.companies.serializers import CompanyBadgeSerializer  # companies imports this module
        return CompanyBadgeSerializer(obj.company).data

    def get_is_saved(self, obj) -> bool:
        # List/retrieve querysets annotate this in one query (see views.py);
        # the fallback covers serializing a single object outside a viewset.
        if hasattr(obj, "user_has_saved"):
            return bool(obj.user_has_saved)
        user = self.context.get("request").user if self.context.get("request") else None
        if not user or not user.is_authenticated:
            return False
        return obj.saved_by.filter(user=user).exists()


class OpportunityDetailSerializer(OpportunitySerializer):
    """One listing in full: adds the description's sections (About the
    organisation, Eligibility, …), which the feed's list views don't need.
    In-app jobs also carry their application requirements, and whether
    the visitor has already applied."""

    requirements = serializers.SerializerMethodField()
    has_applied = serializers.SerializerMethodField()

    class Meta(OpportunitySerializer.Meta):
        fields = OpportunitySerializer.Meta.fields + ["sections", "requirements", "has_applied"]
        read_only_fields = fields

    def get_requirements(self, obj):
        if obj.application_method != Opportunity.ApplicationMethod.IN_APP:
            return []
        from apps.companies.serializers import RequirementSerializer
        return RequirementSerializer(obj.requirements.all(), many=True).data

    def get_has_applied(self, obj) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if obj.application_method != Opportunity.ApplicationMethod.IN_APP or not user or not user.is_authenticated:
            return False
        return obj.applications.filter(applicant=user).exists()


class ModerationOpportunitySerializer(OpportunityDetailSerializer):
    """The moderation queue's view: every requirement (for any method) and
    which of them ask about protected characteristics."""

    flagged_terms = serializers.SerializerMethodField()

    class Meta(OpportunityDetailSerializer.Meta):
        fields = OpportunityDetailSerializer.Meta.fields + ["flagged_terms"]
        read_only_fields = fields

    def get_flagged_terms(self, obj):
        from apps.companies.services import flagged_terms
        return flagged_terms(obj.requirements.all())


class SubmittedSectionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[k for k in KINDS if k != "overview"])
    body = serializers.CharField(max_length=5000, allow_blank=True, trim_whitespace=True)


class OpportunityCreateSerializer(serializers.ModelSerializer):
    """Write serializer for user submissions — deliberately excludes
    status/reviewed_by/published_at/etc; those are only ever set by
    services.approve_opportunity()/reject_opportunity(), never by the
    submitter directly.

    `sections` takes the form's optional fields as [{"kind", "body"}] —
    plain text, one paragraph per line, "- " for bullets — and stores them
    in the structured shape (opportunities/sections.py)."""

    sections = SubmittedSectionSerializer(many=True, required=False, write_only=True)

    class Meta:
        model = Opportunity
        fields = [
            "id", "title", "organization", "description", "location",
            "opportunity_url", "application_deadline", "category", "sections",
        ]
        read_only_fields = ["id"]

    def validate_sections(self, value):
        return clean_sections([
            {"kind": item["kind"], "blocks": text_to_blocks(item["body"])} for item in value if item["body"]
        ])

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["sections"] = instance.sections
        return data


class OpportunityRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False)


class SavedOpportunitySerializer(serializers.ModelSerializer):
    opportunity = OpportunitySerializer(read_only=True)

    class Meta:
        model = SavedOpportunity
        fields = ["id", "opportunity", "saved_at"]
        read_only_fields = fields
