from django.contrib import admin, messages

from .models import (
    Application, ApplicationAnswer, ApplicationRequirement, Company, CompanyInvitation, CompanyMembership, ExportLog,
)
from .services import review_company


class MembershipInline(admin.TabularInline):
    model = CompanyMembership
    extra = 0
    fields = ("user", "role", "invited_by", "created_at")
    readonly_fields = ("invited_by", "created_at")
    raw_id_fields = ("user",)


class InvitationInline(admin.TabularInline):
    model = CompanyInvitation
    extra = 0
    fields = ("email", "role", "invited_by", "created_at", "expires_at", "accepted_at")
    readonly_fields = fields
    can_delete = True  # deleting an invitation revokes it

    def has_add_permission(self, request, obj=None):
        return False  # invitations carry an emailed token; teams send them from the dashboard


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "is_verified", "member_count", "industry", "created_at")
    list_filter = ("status", "is_verified")
    search_fields = ("name", "memberships__user__email", "website")
    readonly_fields = ("slug", "created_by", "verified_at", "reviewed_by", "reviewed_at", "terms_accepted_at",
                       "created_at", "updated_at")
    actions = ("approve", "verify", "remove_badge", "reject", "suspend")
    inlines = [MembershipInline, InvitationInline]

    @admin.display(description="Team")
    def member_count(self, obj):
        return obj.memberships.count()

    def _review(self, request, queryset, action, done):
        for company in queryset:
            review_company(company, request.user, action, company.rejection_reason)
        messages.success(request, f"{done} {queryset.count()} company(ies). They have been emailed.")

    @admin.action(description="Approve (can post; jobs still moderated)")
    def approve(self, request, queryset):
        self._review(request, queryset, "approve", "Approved")

    @admin.action(description="Give verified badge (approves + jobs publish directly)")
    def verify(self, request, queryset):
        if not request.user.is_superuser:
            messages.error(request, "Only administrators can grant the verified badge.")
            return
        self._review(request, queryset, "verify", "Verified")

    @admin.action(description="Remove verified badge")
    def remove_badge(self, request, queryset):
        if not request.user.is_superuser:
            messages.error(request, "Only administrators can remove the verified badge.")
            return
        for company in queryset:
            review_company(company, request.user, "unverify")

    @admin.action(description="Reject (uses the rejection reason field, emails the company)")
    def reject(self, request, queryset):
        self._review(request, queryset, "reject", "Rejected")

    @admin.action(description="Suspend (stops posting, hides their jobs, emails the company)")
    def suspend(self, request, queryset):
        self._review(request, queryset, "suspend", "Suspended")


class AnswerInline(admin.TabularInline):
    model = ApplicationAnswer
    extra = 0
    readonly_fields = ("label", "kind", "value", "original_filename")
    exclude = ("requirement", "file")  # files are downloaded via the API, never by public URL
    can_delete = False


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("applicant", "opportunity", "status", "submitted_at")
    list_filter = ("status",)
    search_fields = ("applicant__email", "opportunity__title")
    readonly_fields = ("opportunity", "applicant", "consent_at", "submitted_at", "updated_at")
    inlines = [AnswerInline]


@admin.register(ApplicationRequirement)
class ApplicationRequirementAdmin(admin.ModelAdmin):
    list_display = ("label", "opportunity", "kind", "required", "position")
    list_filter = ("kind",)
    search_fields = ("label", "opportunity__title")


@admin.register(ExportLog)
class ExportLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "company", "user_name", "job_title", "format", "row_count")
    list_filter = ("format",)
    search_fields = ("company__name", "user_name", "job_title")
    readonly_fields = [f.name for f in ExportLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
