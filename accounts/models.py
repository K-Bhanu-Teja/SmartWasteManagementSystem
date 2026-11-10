from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models.functions import Lower


def validate_document_size(document):
    if document.size > 5 * 1024 * 1024:
        raise ValidationError("Documents must be 5 MB or smaller.")


def validate_document_type(document):
    extension = document.name.rsplit(".", 1)[-1].lower() if "." in document.name else ""
    header = document.read(8)
    document.seek(0)
    signatures = {
        "pdf": header.startswith(b"%PDF-"),
        "jpg": header.startswith(b"\xff\xd8\xff"),
        "jpeg": header.startswith(b"\xff\xd8\xff"),
        "png": header.startswith(b"\x89PNG\r\n\x1a\n"),
    }
    if not signatures.get(extension, False):
        raise ValidationError("Upload a valid PDF, JPEG, or PNG document.")


class User(AbstractUser):
    class Role(models.TextChoices):
        CITIZEN = "citizen", "Citizen"
        ADMINISTRATOR = "administrator", "Administrator"
        WORKER = "worker", "Worker"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CITIZEN)
    phone = models.CharField(max_length=24, blank=True)
    approved = models.BooleanField(default=True)
    rejected = models.BooleanField(default=False)

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_case_insensitive_unique"),
        ]

    @property
    def is_worker(self):
        return self.role == self.Role.WORKER

    @property
    def is_citizen(self):
        return self.role == self.Role.CITIZEN

    @property
    def is_administrator(self):
        return self.role == self.Role.ADMINISTRATOR or self.is_superuser


class CitizenProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="citizen_profile")
    house_number = models.CharField(max_length=80, blank=True)
    street_locality = models.CharField(max_length=180, blank=True)
    ward_number = models.CharField(max_length=30, blank=True)
    village_name = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return f"Citizen Profile for {self.user.username}"


class WorkerProfile(models.Model):
    class Designation(models.TextChoices):
        DRIVER = "driver", "Driver"
        CLEANER = "cleaner", "Cleaner"
        CREW_LEADER = "crew_leader", "Crew Leader"

    class Availability(models.TextChoices):
        INACTIVE = "INACTIVE", "Inactive"
        ACTIVE = "ACTIVE", "Active"
        ASSIGNED = "ASSIGNED", "Assigned"

    class Gender(models.TextChoices):
        WOMAN = "woman", "Woman"
        MAN = "man", "Man"
        OTHER = "other", "Other"
        PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="worker_profile")
    worker_id = models.CharField(max_length=40, blank=True, default="")
    designation = models.CharField(max_length=30, choices=Designation.choices, default=Designation.CLEANER)
    phone = models.CharField(max_length=24, blank=True, default="")
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=24, choices=Gender.choices, blank=True)
    residential_address = models.CharField(max_length=240, blank=True, default="")
    village_name = models.CharField(max_length=120, blank=True, default="")
    ward_number = models.CharField(max_length=30, blank=True, default="")
    experience_years = models.PositiveSmallIntegerField(null=True, blank=True)
    identification_document = models.FileField(
        upload_to="worker_identification/%Y/%m/",
        blank=True,
        null=True,
        validators=[FileExtensionValidator(["pdf", "jpg", "jpeg", "png"]), validate_document_size],
    )
    availability = models.CharField(
        max_length=20,
        choices=Availability.choices,
        default=Availability.INACTIVE,
    )
    availability_updated_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.get_designation_display()})"


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_otps")
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
