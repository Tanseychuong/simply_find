from django.contrib import admin

from .models import DriveRegistration, RecruitmentDrive


class RegistrationInline(admin.TabularInline):
    model = DriveRegistration
    extra = 0
    fields = ("student", "method", "registered_by", "desk_consent_at", "claimed_at", "created_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(RecruitmentDrive)
class RecruitmentDriveAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "code", "location", "starts_on", "ends_on", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "company__name", "code", "location")
    readonly_fields = ("slug", "code", "created_by", "created_at")
    filter_horizontal = ("opportunities",)
    inlines = [RegistrationInline]
