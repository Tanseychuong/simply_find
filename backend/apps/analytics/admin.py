from django.contrib import admin

from .countries import COUNTRY_NAMES, country_name
from .models import PageView, Visitor


class ReadOnlyAdmin(admin.ModelAdmin):
    """Recorded by the site itself — staff can browse and delete, not edit."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class CountryFilter(admin.SimpleListFilter):
    """The countries that actually appear, by name rather than ISO code."""

    title = "country"
    parameter_name = "country"

    def lookups(self, request, model_admin):
        codes = model_admin.get_queryset(request).exclude(country="").values_list("country", flat=True).distinct()
        return sorted(((c, country_name(c)) for c in codes), key=lambda pair: pair[1])

    def queryset(self, request, queryset):
        return queryset.filter(country=self.value()) if self.value() else queryset


@admin.register(Visitor)
class VisitorAdmin(ReadOnlyAdmin):
    list_display = ("__str__", "visit_count", "first_source", "first_seen", "last_seen", "user")
    list_filter = ("first_source",)
    list_select_related = ("user",)
    search_fields = ("user__email", "first_source")
    date_hierarchy = "last_seen"


@admin.register(PageView)
class PageViewAdmin(ReadOnlyAdmin):
    list_display = ("created_at", "path", "source", "starts_visit", "ip_address", "country_display", "visitor")
    list_filter = ("starts_visit", "source", CountryFilter)
    fields = ("created_at", "visitor", "path", "starts_visit", "source", "ip_address", "country_display")
    search_fields = ("path", "source", "ip_address")
    date_hierarchy = "created_at"

    @admin.display(description="country", ordering="country")
    def country_display(self, obj):
        return f"{country_name(obj.country)} ({obj.country})" if obj.country in COUNTRY_NAMES else obj.country
