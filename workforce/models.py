from django.conf import settings
from django.db import models


class Vehicle(models.Model):
    registration_number = models.CharField(max_length=40, unique=True)
    vehicle_type = models.CharField(max_length=80, blank=True)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.registration_number} ({self.vehicle_type or 'Vehicle'})"


class VehicleAssignment(models.Model):
    vehicle = models.ForeignKey(Vehicle, on_delete=models.CASCADE, related_name="assignments")
    driver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="driver_vehicle_assignments")
    is_active = models.BooleanField(default=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.vehicle.registration_number} -> {self.driver.get_full_name() or self.driver.username} ({'Active' if self.is_active else 'Released'})"


class Crew(models.Model):
    name = models.CharField(max_length=80)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_crews",
        null=True,
        blank=True,
    )
    crew_leader = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="led_crews")
    is_active = models.BooleanField(default=True)
    started_at = models.DateTimeField(auto_now_add=True)
    dissolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Dissolved'})"


class CrewMember(models.Model):
    crew = models.ForeignKey(Crew, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="crew_assignments")
    member_type = models.CharField(max_length=20, default="worker")
    is_leader = models.BooleanField(default=False)
    joined_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["joined_at"]

    def __str__(self):
        return f"{self.user.username} in {self.crew.name}"


class Task(models.Model):
    class Category(models.TextChoices):
        DUSTBIN_CLEANING = "Dustbin Cleaning", "Dustbin Cleaning"
        COMPLAINT_RESOLUTION = "Complaint Resolution", "Complaint Resolution"
        HOUSEHOLD_COLLECTION = "Household Waste Collection", "Household Waste Collection"
        AREA_CLEANING = "Area Cleaning", "Area Cleaning"
        EMERGENCY_CLEANING = "Emergency Cleaning", "Emergency Cleaning"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ASSIGNED = "ASSIGNED", "Assigned"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    title = models.CharField(max_length=150)
    category = models.CharField(max_length=50, choices=Category.choices)
    description = models.TextField()
    request = models.OneToOneField(
        "citizen_services.Request",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="task",
    )
    dustbin = models.ForeignKey(
        "citizen_services.Dustbin",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    assigned_worker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="direct_tasks",
    )
    assigned_crew = models.ForeignKey(
        Crew,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tasks",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tasks",
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    location_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    due_date = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_photo = models.ImageField(upload_to="task_completions/%Y/%m/", null=True, blank=True)
    completion_remarks = models.TextField(blank=True)
    verified_by_admin = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Task #{self.pk}: {self.title} ({self.get_status_display()})"


class Notification(models.Model):
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    message = models.CharField(max_length=240)
    link = models.CharField(max_length=255, blank=True, default="")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification for {self.recipient.username}: {self.message[:30]}"
