from django.contrib import admin

from .models import CleaningHistory, Dustbin, Request


@admin.register(Dustbin)
class DustbinAdmin(admin.ModelAdmin):
    list_display = ("name", "description", "latitude", "longitude", "is_active", "last_cleaned_at")
    list_filter = ("is_active", "last_cleaned_at")
    search_fields = ("name", "description")


@admin.register(Request)
class RequestAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "citizen", "cause", "status", "created_at")
    list_filter = ("status", "cause", "created_at")
    search_fields = ("title", "citizen__username", "citizen__email", "description")


@admin.register(CleaningHistory)
class CleaningHistoryAdmin(admin.ModelAdmin):
    list_display = ("dustbin", "cleaned_by", "cleaned_at", "task")
    list_filter = ("cleaned_at",)
    search_fields = ("dustbin__name", "remarks")
