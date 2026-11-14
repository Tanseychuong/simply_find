from django.contrib import admin
from django.db.models import Count

from config.admin_site import pill

from .models import FetchLog, FetchSource
from .services import fetch_source

LOG_TONE = {FetchLog.Status.SUCCESS: "ok", FetchLog.Status.PARTIAL: "warn", FetchLog.Status.FAILURE: "bad"}


@admin.action(description="Fetch now", permissions=["change"])
def fetch_now(modeladmin, request, queryset):
    for source in queryset:
        log = fetch_source(source)
        modeladmin.message_user(
            request,
            f"{source.name}: {log.status} — found {log.items_found}, created {log.items_created}"
            + (f" — {log.error_message}" if log.error_message else ""),
        )


@admin.action(description="Fetch on the worker's next cycle", permissions=["change"])
def fetch_next_cycle(modeladmin, request, queryset):
    count = queryset.update(next_fetch_at=None)
    modeladmin.message_user(request, f"{count} source(s) will be fetched on the worker's next cycle.")


@admin.register(FetchSource)
class FetchSourceAdmin(admin.ModelAdmin):
    list_display = (
        "name", "connector_type", "category", "is_active", "health",
        "fetch_interval_minutes", "last_fetched_at", "next_fetch_at", "listings",
    )
    list_filter = ("connector_type", "is_active", "category")
    list_select_related = ("category",)
    search_fields = ("name", "url")
    autocomplete_fields = ("category",)
    readonly_fields = ("last_fetched_at", "consecutive_failures", "last_error", "created_at")
    actions = [fetch_now, fetch_next_cycle]
    fieldsets = (
        (None, {"fields": ("name", "connector_type", "url", "category", "include_keywords", "is_active")}),
        ("Automatic schedule", {"fields": ("fetch_interval_minutes", "next_fetch_at", "last_fetched_at")}),
        ("Health", {"fields": ("consecutive_failures", "last_error", "created_at")}),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(listings_n=Count("opportunities"))

    @admin.display(description="Health", ordering="consecutive_failures")
    def health(self, obj):
        if obj.consecutive_failures:
            n = obj.consecutive_failures
            return pill(f"{n} failure{'s' if n != 1 else ''}", "bad")
        if obj.last_fetched_at is None:
            return pill("Not fetched yet")
        return pill("OK", "ok")

    @admin.display(description="Listings", ordering="listings_n")
    def listings(self, obj):
        return obj.listings_n


@admin.register(FetchLog)
class FetchLogAdmin(admin.ModelAdmin):
    list_display = ("source", "status_badge", "items_found", "items_created", "started_at", "duration")
    list_filter = ("status", "source")
    list_select_related = ("source",)
    date_hierarchy = "started_at"
    readonly_fields = [f.name for f in FetchLog._meta.fields]  # history record, never hand-edited

    def has_add_permission(self, request):
        return False  # logs are only ever created by fetch_source(), never by hand

    def has_change_permission(self, request, obj=None):
        return False  # view-only: drops the useless Save buttons

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        return pill(obj.get_status_display(), LOG_TONE.get(obj.status, "quiet"))

    @admin.display(description="Took")
    def duration(self, obj):
        return f"{(obj.finished_at - obj.started_at).total_seconds():.1f}s"
