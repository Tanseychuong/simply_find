"""
Registers User with the Django admin. This IS the admin's user-management
UI — including where you'll assign the "Moderators" group to specific
users, once that group exists (created in opportunities/models.py's
migration or manually in /admin/auth/group/).
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import UserCreationForm, UserChangeForm
from .models import User


@admin.action(description="Grant premium (no expiry)", permissions=["change"])
def grant_premium(modeladmin, request, queryset):
    count = queryset.update(is_premium=True, premium_expires_at=None)
    modeladmin.message_user(request, f"Granted premium to {count} user(s).")


@admin.action(description="Revoke premium", permissions=["change"])
def revoke_premium(modeladmin, request, queryset):
    count = queryset.update(is_premium=False, premium_expires_at=None)
    modeladmin.message_user(request, f"Revoked premium from {count} user(s).")


@admin.action(description="Restore account (cancel a deletion request)", permissions=["change"])
def restore_account(modeladmin, request, queryset):
    from .deletion import restore

    pending = queryset.filter(deletion_requested_at__isnull=False)
    for user in pending:
        restore(user)
    modeladmin.message_user(
        request, f"Restored {pending.count()} account(s). Re-approve any company they own from Companies if needed.",
    )


@admin.action(description="Unlink Google sign-in", permissions=["change"])
def unlink_google(modeladmin, request, queryset):
    # For a user who lost their Google account: they can then use
    # "Forgot password" (it works for Google-only accounts) or link a new one.
    count = queryset.exclude(google_sub=None).update(google_sub=None)
    modeladmin.message_user(request, f"Unlinked Google from {count} account(s).")


class UserAdmin(BaseUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm
    model = User

    ordering = ("email",)
    list_display = ("email", "name", "is_staff", "is_superuser", "premium_active", "created_at", "deletion_requested_at")
    list_filter = ("is_staff", "is_superuser", "is_premium", "is_active", "groups")
    search_fields = ("email", "name")
    readonly_fields = ("created_at", "deletion_requested_at", "google_sub")
    date_hierarchy = "created_at"
    actions = [grant_premium, revoke_premium, restore_account, unlink_google]

    # Deleting someone here must not take the company jobs they posted with
    # them (Opportunity.posted_by cascades); those pass to the company's team.
    def delete_model(self, request, obj):
        from apps.companies.services import keep_company_jobs
        keep_company_jobs(obj)
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        from apps.companies.services import keep_company_jobs
        for user in queryset:
            keep_company_jobs(user)
        super().delete_queryset(request, queryset)

    @admin.display(description="Premium", boolean=True)
    def premium_active(self, obj):
        # is_premium alone stays True after premium_expires_at passes.
        return obj.is_premium_active()

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("name", "profile_picture")}),
        ("Google sign-in", {"fields": ("google_sub",)}),
        ("Premium", {"fields": ("is_premium", "premium_expires_at")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active", "is_staff", "is_superuser",
                    "groups", "user_permissions",   # <- assign "Moderators" group here
                ),
            },
        ),
        ("Important dates", {"fields": ("created_at", "deletion_requested_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "name", "password1", "password2"),
            },
        ),
    )


admin.site.register(User, UserAdmin)
