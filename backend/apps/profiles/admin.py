from django.contrib import admin

from .models import StudentProfile


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "institution", "graduation_year", "country", "updated_at")
    list_filter = ("status", "country", "graduation_year")
    search_fields = ("user__email", "user__name", "institution", "programme")
    raw_id_fields = ("user",)
