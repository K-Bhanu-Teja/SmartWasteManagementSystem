from django.contrib import admin

from .models import Crew, CrewMember, Notification, Task, Vehicle, VehicleAssignment


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("registration_number", "vehicle_type", "is_available", "created_at")
    search_fields = ("registration_number", "vehicle_type")
    list_filter = ("is_available",)


@admin.register(VehicleAssignment)
class VehicleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("vehicle", "driver", "is_active", "assigned_at", "released_at")
    list_filter = ("is_active", "assigned_at")
    search_fields = ("vehicle__registration_number", "driver__username", "driver__email")


@admin.register(Crew)
class CrewAdmin(admin.ModelAdmin):
    list_display = ("name", "crew_leader", "is_active", "started_at", "dissolved_at", "created_by")
    list_filter = ("is_active", "started_at")
    search_fields = ("name", "crew_leader__username")


@admin.register(CrewMember)
class CrewMemberAdmin(admin.ModelAdmin):
    list_display = ("crew", "user", "member_type", "is_leader", "is_active", "joined_at", "released_at")
    list_filter = ("is_leader", "is_active")
    search_fields = ("crew__name", "user__username")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "category", "status", "assigned_worker", "assigned_crew", "verified_by_admin", "created_at")
    list_filter = ("status", "category", "verified_by_admin", "created_at")
    search_fields = ("title", "description", "location_name")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "message", "is_read", "created_at")
    list_filter = ("is_read", "created_at")
    search_fields = ("recipient__username", "message")
