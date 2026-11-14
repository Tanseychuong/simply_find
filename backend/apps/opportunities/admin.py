"""
This admin interface IS the moderation queue — the whole reason we chose
Django. Filter by status=pending, select rows, "Approve selected" /
"Reject selected" — no custom frontend needed for moderators to work from
day one. A real admin UI can be built later without this ever blocking
launch.

Every status change — bulk action or the change form's dropdown — goes
through Opportunity.approve()/reject(), so published_at and
the reviewer trail are always set the same way as from the API.
"""

from django.contrib import admin, messages
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html

from config.admin_site import pill

from .models import Opportunity, OpportunityCategory, SavedOpportunity
from .sections import clean_sections

STATUS_TONE = {
    Opportunity.Status.PENDING: "warn",
    Opportunity.Status.APPROVED: "ok",
    Opportunity.Status.REJECTED: "bad",
}
ENRICHMENT_TONE = {
    Opportunity.EnrichmentStatus.PENDING: "warn",
    Opportunity.EnrichmentStatus.DONE: "ok",
    Opportunity.EnrichmentStatus.FAILED: "bad",
    Opportunity.EnrichmentStatus.SKIPPED: "quiet",
}


def _plural(count):
    return f"{count} opportunit{'y' if count == 1 else 'ies'}"


@admin.register(OpportunityCategory)
class OpportunityCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_active", "listings")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(listings_n=Count("opportunities"))

    @admin.display(description="Listings", ordering="listings_n")
    def listings(self, obj):
        return obj.listings_n


@admin.action(description="Approve selected opportunities", permissions=["verify"])
def approve_opportunities(modeladmin, request, queryset):
    # Re-approving a live listing would reset its early-access window.
    to_approve = queryset.exclude(status=Opportunity.Status.APPROVED)
    count = 0
    for opportunity in to_approve:
        opportunity.approve(reviewer=request.user)
        count += 1
    skipped = queryset.count() - count
    modeladmin.message_user(
        request, f"Approved {_plural(count)}." + (f" Skipped {skipped} already approved." if skipped else ""),
    )


@admin.action(description="Reject selected opportunities", permissions=["verify"])
def reject_opportunities(modeladmin, request, queryset):
    to_reject = queryset.exclude(status=Opportunity.Status.REJECTED)
    skipped = queryset.count() - to_reject.count()
    count = to_reject.update(
        status=Opportunity.Status.REJECTED,
        reviewed_by=request.user,
        reviewed_at=timezone.now(),
        rejection_reason="Rejected in bulk from the admin queue.",
    )
    modeladmin.message_user(
        request, f"Rejected {_plural(count)}." + (f" Skipped {skipped} already rejected." if skipped else ""),
    )


@admin.action(description="Re-fetch image and summary")
def reenrich_opportunities(modeladmin, request, queryset):
    count = queryset.update(
        enrichment_status=Opportunity.EnrichmentStatus.PENDING,
        enrichment_attempts=0,
        enrichment_checked_at=None,
    )
    modeladmin.message_user(request, f"{_plural(count)} queued for the worker.")


@admin.register(Opportunity)
class OpportunityAdmin(admin.ModelAdmin):
    list_display = (
        "title", "organization", "category", "status_badge", "source_type", "enrichment_badge",
        "submitted_at", "application_deadline", "saves",
    )
    list_filter = ("status", "role_type", "source_type", "enrichment_status", "category")
    list_select_related = ("category",)
    search_fields = ("title", "organization", "description", "opportunity_url", "listing_url")
    date_hierarchy = "submitted_at"
    ordering = ("-submitted_at",)
    list_per_page = 50
    autocomplete_fields = ("category",)
    raw_id_fields = ("posted_by", "fetch_source")
    readonly_fields = (
        "submitted_at", "reviewed_by", "reviewed_at",
        "published_at", "open_link",
        "image_preview", "enrichment_status", "enrichment_attempts", "enrichment_checked_at",
        "source_published_at", "listing_link",
    )
    actions = [approve_opportunities, reject_opportunities, reenrich_opportunities]

    fieldsets = (
        (None, {"fields": ("title", "organization", "category", "description", "location", "opportunity_url", "open_link", "application_deadline")}),
        ("Who it's for", {"fields": (
            "role_type", "experience_years_max", ("graduation_year_min", "graduation_year_max"),
            "is_paid", "work_mode", "duration_months", "accepts_minors",
        )}),
        ("Description sections", {
            "fields": ("sections",),
            "classes": ("collapse",),
            "description": "About the organisation, Eligibility, Benefits, How to apply … as shown on the "
                           "listing page. Filled automatically for fetched listings; edits are tidied on save.",
        }),
        ("Cover image", {"fields": ("image_url", "image_preview")}),
        ("Source", {"fields": ("posted_by", "source_type", "fetch_source", "listing_link", "source_published_at")}),
        ("Moderation", {
            "fields": ("status", "rejection_reason", "submitted_at", "reviewed_by", "reviewed_at"),
            "description": "Changing the status here approves or rejects the listing exactly like the bulk actions.",
        }),
        ("Publishing", {"fields": ("published_at",)}),
        ("Automatic enrichment", {"fields": ("enrichment_status", "enrichment_attempts", "enrichment_checked_at")}),
    )

    def has_verify_permission(self, request):
        return request.user.has_perm("opportunities.can_verify_opportunity")

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if not self.has_verify_permission(request):
            fields = (*fields, "status", "rejection_reason")
        return fields

    def save_model(self, request, obj, form, change):
        obj.sections = clean_sections(obj.sections)
        if "status" in form.changed_data:
            if obj.status == Opportunity.Status.APPROVED:
                obj.approve(reviewer=request.user)
                return
            if obj.status == Opportunity.Status.REJECTED:
                obj.reject(request.user, obj.rejection_reason or "Rejected from the admin.")
                return
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(saves_n=Count("saved_by"))

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        return pill(obj.get_status_display(), STATUS_TONE.get(obj.status, "quiet"))

    @admin.display(description="Enrichment", ordering="enrichment_status")
    def enrichment_badge(self, obj):
        return pill(obj.get_enrichment_status_display(), ENRICHMENT_TONE.get(obj.enrichment_status, "quiet"))

    @admin.display(description="Saves", ordering="saves_n")
    def saves(self, obj):
        return obj.saves_n

    @admin.display(description="Open listing")
    def open_link(self, obj):
        if not obj.opportunity_url:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">{} ↗</a>', obj.opportunity_url, obj.opportunity_url)

    @admin.display(description="Posted at")
    def listing_link(self, obj):
        if not obj.listing_url:
            return "—"
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">{} ↗</a>', obj.listing_url, obj.listing_url)

    @admin.display(description="Preview")
    def image_preview(self, obj):
        if not obj.image_url:
            return "—"
        return format_html('<img src="{}" style="max-width:320px;max-height:180px;object-fit:cover" referrerpolicy="no-referrer">', obj.image_url)


@admin.register(SavedOpportunity)
class SavedOpportunityAdmin(admin.ModelAdmin):
    list_display = ("user", "opportunity", "saved_at")
    list_select_related = ("user", "opportunity")
    list_filter = ("opportunity__category",)
    search_fields = ("user__email", "opportunity__title")
    date_hierarchy = "saved_at"
    raw_id_fields = ("user", "opportunity")
