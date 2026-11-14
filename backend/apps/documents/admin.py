from django.contrib import admin

from .models import Credential, Document, DocumentAccess


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    """Metadata only: the files themselves stay in private storage."""
    list_display = ("title", "kind", "owner", "size", "uploaded_by", "created_at")
    list_filter = ("kind",)
    search_fields = ("title", "owner__email")
    fields = ("owner", "kind", "title", "original_filename", "content_type", "size", "sha256",
              "uploaded_by", "consent_at", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request):
        return False


@admin.register(Credential)
class CredentialAdmin(admin.ModelAdmin):
    list_display = ("title", "provider", "owner", "check_status", "checked_at")
    list_filter = ("provider", "check_status")
    search_fields = ("title", "issuer", "owner__email")
    readonly_fields = ("owner", "check_status", "check_detail", "checked_at", "created_at")


@admin.register(DocumentAccess)
class DocumentAccessAdmin(admin.ModelAdmin):
    list_display = ("accessed_at", "viewer_name", "company_name", "owner", "label")
    search_fields = ("owner__email", "viewer_name", "company_name")
    readonly_fields = [f.name for f in DocumentAccess._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
