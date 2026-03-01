from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = (
        "email",
        "username",
        "billing_tier",
        "is_staff",
        "is_superuser",
        "is_active",
        "created_at",
    )
    search_fields = ("email", "username", "company_name")
    list_filter = ("billing_tier", "is_staff", "is_superuser", "is_active")
    ordering = ("email",)
    readonly_fields = ("created_at",)

    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Billing",
            {"fields": ("billing_tier", "company_name", "created_at")},
        ),
    )
