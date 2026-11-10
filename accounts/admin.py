from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import CitizenProfile, PasswordResetOTP, User, WorkerProfile


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (
        ("SWMS access", {"fields": ("role", "phone", "approved")}),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ("SWMS access", {"fields": ("email", "role", "phone", "approved")}),
    )
    list_display = ("username", "email", "role", "approved", "is_active", "is_staff")
    list_filter = ("role", "approved", "is_active")


@admin.register(CitizenProfile)
class CitizenProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "house_number", "street_locality", "ward_number", "village_name")
    search_fields = ("user__username", "user__email", "village_name", "ward_number")


@admin.register(WorkerProfile)
class WorkerProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "worker_id", "designation", "phone", "availability", "availability_updated_at")
    list_filter = ("designation", "availability")
    search_fields = ("user__username", "user__email", "worker_id", "phone")


@admin.register(PasswordResetOTP)
class PasswordResetOTPAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "expires_at", "used_at", "attempts")
    readonly_fields = ("code_hash", "created_at", "expires_at", "used_at", "attempts")
