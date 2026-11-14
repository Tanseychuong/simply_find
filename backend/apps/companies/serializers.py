from rest_framework import serializers

from apps.opportunities.models import Opportunity, OpportunityCategory
from apps.opportunities.serializers import ROLE_FIELDS, EntryLevelRulesMixin
from apps.opportunities.sections import KINDS, clean_sections, text_to_blocks

from .models import Application, ApplicationAnswer, ApplicationRequirement, Company, CompanyInvitation, CompanyMembership


class CompanyBadgeSerializer(serializers.ModelSerializer):
    """What a job listing shows about the company that posted it."""

    class Meta:
        model = Company
        fields = ["id", "name", "slug", "logo_url", "is_verified"]
        read_only_fields = fields


class CompanyPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = [
            "id", "name", "slug", "website", "logo_url", "description", "industry",
            "location", "size", "is_verified", "created_at",
        ]
        read_only_fields = fields


class CompanyOwnerSerializer(serializers.ModelSerializer):
    """The company's own view of its profile, including review status."""

    can_post = serializers.BooleanField(read_only=True)
    publishes_directly = serializers.BooleanField(read_only=True)
    # Required when signing up: the person may act for the company, and will
    # use applicant data only to recruit for the role applied to.
    accept_terms = serializers.BooleanField(write_only=True, required=False)

    def validate(self, attrs):
        accepted = attrs.pop("accept_terms", False)
        if self.instance is None and not accepted:
            raise serializers.ValidationError({"accept_terms": "Please confirm the hiring commitments to continue."})
        return attrs

    class Meta:
        model = Company
        fields = [
            "id", "name", "slug", "website", "logo_url", "description", "industry", "location",
            "size", "contact_email", "status", "is_verified", "rejection_reason",
            "can_post", "publishes_directly", "created_at", "accept_terms",
        ]
        read_only_fields = [
            "id", "slug", "status", "is_verified", "rejection_reason", "can_post", "publishes_directly", "created_at",
        ]


class RequirementSerializer(serializers.ModelSerializer):
    options = serializers.ListField(
        child=serializers.CharField(max_length=200), required=False, allow_empty=True, max_length=20,
    )

    class Meta:
        model = ApplicationRequirement
        fields = ["id", "label", "kind", "help_text", "required", "options"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        options = [o.strip() for o in attrs.get("options", []) if o.strip()]
        if attrs.get("kind") == ApplicationRequirement.Kind.CHOICE:
            if len(options) < 2:
                raise serializers.ValidationError({"options": "Give at least two choices."})
        else:
            options = []
        attrs["options"] = options
        return attrs


class SubmittedSectionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=[k for k in KINDS if k != "overview"])
    body = serializers.CharField(max_length=5000, allow_blank=True, trim_whitespace=True)


class CompanyJobCreateSerializer(EntryLevelRulesMixin, serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=OpportunityCategory.objects.filter(is_active=True))
    sections = SubmittedSectionSerializer(many=True, required=False)
    requirements = RequirementSerializer(many=True, required=False, max_length=30)

    class Meta:
        model = Opportunity
        fields = [
            "title", "description", "location", "opportunity_url", "application_deadline",
            "category", "sections", "application_method", "requirements",
        ] + ROLE_FIELDS

    def validate_sections(self, value):
        return clean_sections([
            {"kind": item["kind"], "blocks": text_to_blocks(item["body"])} for item in value if item["body"]
        ])


class CompanyJobUpdateSerializer(CompanyJobCreateSerializer):
    """Editing a job: every field optional. `requirements`, when sent,
    replaces the whole list (only allowed before anyone applies)."""

    def __init__(self, *args, **kwargs):
        kwargs["partial"] = True
        super().__init__(*args, **kwargs)


class CompanyJobSerializer(serializers.ModelSerializer):
    """A job as the company that posted it sees it: every status, with counts."""

    category = serializers.CharField(source="category.name", read_only=True)
    category_id = serializers.IntegerField(read_only=True)
    application_count = serializers.IntegerField(read_only=True, default=0)
    requirements = RequirementSerializer(many=True, read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    flagged_terms = serializers.SerializerMethodField()

    class Meta:
        model = Opportunity
        fields = [
            "id", "title", "description", "sections", "location", "category", "category_id", "status",
            "rejection_reason", "application_method", "opportunity_url", "application_deadline",
            "published_at", "submitted_at", "is_open", "application_count", "requirements", "flagged_terms",
        ] + ROLE_FIELDS
        read_only_fields = fields

    def get_flagged_terms(self, obj):
        from .services import flagged_terms
        return flagged_terms(obj.requirements.all())


class CompanyReviewSerializer(serializers.ModelSerializer):
    """A company as moderators review it. `created_by_*` is the person who
    signed it up and accepted the hiring commitments."""

    created_by_name = serializers.CharField(source="created_by.name", read_only=True, default=None)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True, default=None)
    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            "id", "name", "slug", "website", "logo_url", "description", "industry", "location", "size",
            "contact_email", "created_by_name", "created_by_email", "member_count", "status", "is_verified",
            "rejection_reason", "terms_accepted_at", "created_at",
        ]
        read_only_fields = fields

    def get_member_count(self, obj) -> int:
        count = getattr(obj, "member_count", None)
        return count if count is not None else obj.memberships.count()


class TeamMemberSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="user.name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    invited_by = serializers.CharField(source="invited_by.name", read_only=True, default=None)
    is_you = serializers.SerializerMethodField()

    class Meta:
        model = CompanyMembership
        fields = ["id", "name", "email", "role", "invited_by", "is_you", "created_at"]
        read_only_fields = fields

    def get_is_you(self, obj) -> bool:
        request = self.context.get("request")
        return bool(request and obj.user_id == request.user.pk)


class CompanyInvitationSerializer(serializers.ModelSerializer):
    invited_by = serializers.CharField(source="invited_by.name", read_only=True, default=None)

    class Meta:
        model = CompanyInvitation
        fields = ["id", "email", "role", "invited_by", "created_at", "expires_at"]
        read_only_fields = fields


class InviteSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=CompanyMembership.Role.choices, default=CompanyMembership.Role.RECRUITER)


class CompanyReviewActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "verify", "unverify", "reject", "suspend"])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        if attrs["action"] in ("reject", "suspend") and not attrs.get("reason", "").strip():
            raise serializers.ValidationError({"reason": "Tell the company why."})
        return attrs


class AnswerSerializer(serializers.ModelSerializer):
    has_file = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationAnswer
        fields = ["id", "label", "kind", "value", "has_file", "original_filename"]
        read_only_fields = fields

    def get_has_file(self, obj) -> bool:
        return bool(obj.file)


CONTACT_VISIBLE_STATUSES = {Application.Status.SHORTLISTED, Application.Status.HIRED}


def applicant_for_company(application) -> dict:
    """Who applied, as the hiring team sees them. Contact details stay
    hidden until the team shortlists the applicant, so companies judge the
    application first, and nobody harvests a list of student emails by
    posting a role."""
    visible = application.status in CONTACT_VISIBLE_STATUSES
    user = application.applicant
    return {
        "id": user.pk,
        "name": user.name,
        "email": user.email if visible else None,
        "contact_visible": visible,
    }


class CompanyApplicationSerializer(serializers.ModelSerializer):
    """An application as the hiring company sees it."""

    applicant = serializers.SerializerMethodField()
    answers = AnswerSerializer(many=True, read_only=True)
    job_title = serializers.CharField(source="opportunity.title", read_only=True)

    class Meta:
        model = Application
        fields = ["id", "job_title", "applicant", "status", "company_note", "submitted_at", "answers"]
        read_only_fields = ["id", "job_title", "applicant", "submitted_at", "answers"]

    def get_applicant(self, obj) -> dict:
        return applicant_for_company(obj)

    def validate_status(self, value):
        if value == Application.Status.WITHDRAWN:
            raise serializers.ValidationError("Only the applicant can withdraw.")
        return value


class MyApplicationSerializer(serializers.ModelSerializer):
    """An application as the applicant sees it — no private company note."""

    answers = AnswerSerializer(many=True, read_only=True)
    job = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = ["id", "job", "status", "submitted_at", "answers"]
        read_only_fields = fields

    def get_job(self, obj):
        o = obj.opportunity
        return {
            "id": o.id, "title": o.title, "organization": o.organization,
            "company": CompanyBadgeSerializer(o.company).data if o.company_id else None,
        }
