from django.utils import timezone
from rest_framework import serializers

from apps.companies.serializers import CompanyBadgeSerializer
from apps.opportunities.models import Opportunity

from .models import DriveRegistration, RecruitmentDrive


class DriveSerializer(serializers.ModelSerializer):
    """The company's own view of a drive."""

    opportunities = serializers.PrimaryKeyRelatedField(many=True, queryset=Opportunity.objects.none(), required=False)
    public_url = serializers.CharField(read_only=True)
    registration_count = serializers.IntegerField(read_only=True, default=0)
    claimed_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = RecruitmentDrive
        fields = ["id", "name", "slug", "code", "location", "starts_on", "ends_on", "description", "opportunities",
                  "is_active", "public_url", "registration_count", "claimed_count", "created_at"]
        read_only_fields = ["id", "slug", "code", "public_url", "registration_count", "claimed_count", "created_at"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["opportunities"].child_relation.queryset = Opportunity.objects.filter(company=company)

    def validate(self, attrs):
        starts = attrs.get("starts_on", getattr(self.instance, "starts_on", None))
        ends = attrs.get("ends_on", getattr(self.instance, "ends_on", None))
        if starts and ends and ends < starts:
            raise serializers.ValidationError({"ends_on": "The drive can't end before it starts."})
        if ends and self.instance is None and ends < timezone.localdate():
            raise serializers.ValidationError({"ends_on": "This date has passed."})
        return attrs


class PublicDriveSerializer(serializers.ModelSerializer):
    company = CompanyBadgeSerializer(read_only=True)
    jobs = serializers.SerializerMethodField()

    class Meta:
        model = RecruitmentDrive
        fields = ["name", "code", "location", "starts_on", "ends_on", "description", "company", "jobs"]
        read_only_fields = fields

    def get_jobs(self, drive):
        user = self.context["request"].user
        return [
            {"id": job.pk, "title": job.title, "role_type": job.role_type, "work_mode": job.work_mode,
             "application_deadline": job.application_deadline, "application_method": job.application_method}
            for job in drive.opportunities.all() if job.is_visible_to(user) and job.is_open
        ]


class RegistrationSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.name", read_only=True)
    student_email = serializers.CharField(source="student.email", read_only=True)
    registered_by_name = serializers.CharField(source="registered_by.name", read_only=True, default=None)
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = DriveRegistration
        fields = ["id", "student_name", "student_email", "method", "registered_by_name", "desk_consent_at",
                  "claimed_at", "created_at", "document_count"]
        read_only_fields = fields

    def get_document_count(self, registration):
        return registration.student.documents.count()
