from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Dustbin(models.Model):
    name = models.CharField(max_length=100, blank=True, default="")
    description = models.CharField(max_length=240, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    is_active = models.BooleanField(default=True)
    last_cleaned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if self._state.adding and not self.name:
            super().save(*args, **kwargs)
            self.name = f"DBno{self.pk}"
            super().save(update_fields=["name"])
            return

        if not self.name and self.pk:
            self.name = f"DBno{self.pk}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name or f"Dustbin #{self.pk}"


class CleaningHistory(models.Model):
    dustbin = models.ForeignKey(Dustbin, on_delete=models.CASCADE, related_name="cleaning_history")
    task = models.ForeignKey("workforce.Task", on_delete=models.SET_NULL, null=True, blank=True, related_name="cleaning_records")
    cleaned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="cleaned_dustbins")
    cleaned_at = models.DateTimeField(auto_now_add=True)
    remarks = models.TextField(blank=True)

    class Meta:
        ordering = ["-cleaned_at"]

    def __str__(self):
        return f"Cleaned {self.dustbin.name} at {self.cleaned_at}"


class Request(models.Model):
    class Cause(models.TextChoices):
        OVERFLOWING_DUSTBIN = "Overflowing Dustbin", "Overflowing Dustbin"
        ILLEGAL_GARBAGE_DUMPING = "Illegal Garbage Dumping", "Illegal Garbage Dumping"
        DAMAGED_DUSTBIN = "Damaged Dustbin", "Damaged Dustbin"
        ROADSIDE_GARBAGE = "Roadside Garbage", "Roadside Garbage"
        SCHEDULED_WASTE_PICKUP = "Scheduled Waste Pickup", "Scheduled Waste Pickup"
        OTHER = "Other", "Other"

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        APPROVED = "APPROVED", "Approved"
        ASSIGNED = "ASSIGNED", "Assigned"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        RESOLVED = "RESOLVED", "Resolved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    citizen = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="requests")
    title = models.CharField(max_length=150)
    cause = models.CharField(max_length=50, choices=Cause.choices)
    description = models.TextField()
    photo = models.ImageField(upload_to="requests/%Y/%m/", null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(-90), MaxValueValidator(90)])
    longitude = models.DecimalField(max_digits=9, decimal_places=6, validators=[MinValueValidator(-180), MaxValueValidator(180)])
    address = models.CharField(max_length=255, blank=True)

    # Conditional fields for Scheduled Waste Pickup
    preferred_pickup_date = models.DateField(null=True, blank=True)
    preferred_pickup_time = models.TimeField(null=True, blank=True)
    waste_category = models.CharField(max_length=80, blank=True)

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.SUBMITTED)
    admin_remarks = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Request #{self.pk}: {self.title} ({self.get_status_display()})"
