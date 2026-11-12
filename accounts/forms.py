import re
from uuid import uuid4

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import CitizenProfile, User, WorkerProfile


class EmailAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}),
    )

    def clean(self):
        try:
            return super().clean()
        except ValidationError:
            email = self.cleaned_data.get("username")
            password = self.cleaned_data.get("password")
            user = User.objects.filter(email__iexact=email).first() if email else None
            if user and not user.approved and user.check_password(password or ""):
                raise ValidationError("Your account is awaiting administrator approval.")
            raise


class CitizenRegistrationForm(forms.Form):
    full_name = forms.CharField(
        max_length=180,
        label="Full Name",
        widget=forms.TextInput(attrs={"autocomplete": "name", "placeholder": "Your full name"}),
    )
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"}),
    )
    mobile_number = forms.CharField(
        max_length=24,
        label="Mobile Number",
        widget=forms.TelInput(attrs={"autocomplete": "tel", "placeholder": "9876543210"}),
    )
    house_number = forms.CharField(max_length=80, label="House Number", required=False)
    street_locality = forms.CharField(max_length=180, label="Street / Locality", required=False)
    ward_number = forms.CharField(max_length=30, label="Ward Number", required=False)
    village_name = forms.CharField(max_length=120, label="Village / Area Name", required=False)
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password_confirm = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_mobile_number(self):
        mobile = re.sub(r"[\s-]", "", self.cleaned_data["mobile_number"])
        if not re.fullmatch(r"(?:\+91)?[6-9]\d{9}", mobile):
            raise ValidationError("Enter a valid 10-digit mobile number, optionally prefixed with +91.")
        return mobile

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "The passwords do not match.")
        return cleaned_data

    def save(self):
        first_name, _, last_name = self.cleaned_data["full_name"].strip().partition(" ")
        with transaction.atomic():
            user = User.objects.create_user(
                username=f"citizen-{uuid4().hex[:8]}",
                email=self.cleaned_data["email"],
                phone=self.cleaned_data["mobile_number"],
                first_name=first_name,
                last_name=last_name,
                password=self.cleaned_data["password"],
                role=User.Role.CITIZEN,
                approved=True,
                is_active=True,
            )
            CitizenProfile.objects.create(
                user=user,
                house_number=self.cleaned_data.get("house_number", ""),
                street_locality=self.cleaned_data.get("street_locality", ""),
                ward_number=self.cleaned_data.get("ward_number", ""),
                village_name=self.cleaned_data.get("village_name", ""),
            )
        return user


class WorkerRegistrationForm(forms.Form):
    full_name = forms.CharField(max_length=180, label="Full Name")
    email = forms.EmailField(label="Email Address")
    mobile_number = forms.CharField(max_length=24, label="Mobile Number")
    designation = forms.ChoiceField(
        choices=WorkerProfile.REGISTRATION_DESIGNATIONS,
        label="Job Designation",
    )
    worker_id = forms.CharField(
        max_length=40,
        required=False,
        label="Worker ID (leave blank to auto-generate)",
    )
    residential_address = forms.CharField(
        max_length=240,
        required=False,
        label="Residential Address",
        widget=forms.Textarea(attrs={"rows": 2}),
    )
    password = forms.CharField(
        label="Initial Password",
        widget=forms.PasswordInput(),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def save(self):
        first_name, _, last_name = self.cleaned_data["full_name"].strip().partition(" ")
        with transaction.atomic():
            user = User.objects.create_user(
                username=f"worker-{uuid4().hex[:8]}",
                email=self.cleaned_data["email"],
                phone=self.cleaned_data["mobile_number"],
                first_name=first_name,
                last_name=last_name,
                password=self.cleaned_data["password"],
                role=User.Role.WORKER,
                approved=True,
                is_active=True,
            )
            worker_id = self.cleaned_data.get("worker_id", "").strip() or f"WRK-{user.pk}"
            WorkerProfile.objects.create(
                user=user,
                worker_id=worker_id,
                designation=self.cleaned_data["designation"],
                phone=self.cleaned_data["mobile_number"],
                residential_address=self.cleaned_data.get("residential_address", ""),
                availability=WorkerProfile.Availability.ACTIVE,
            )
        return user


class WorkerUpdateForm(forms.ModelForm):
    full_name = forms.CharField(max_length=180, label="Full Name")
    email = forms.EmailField(label="Email Address")
    phone = forms.CharField(max_length=24, label="Phone")

    class Meta:
        model = WorkerProfile
        fields = ("worker_id", "designation", "residential_address", "availability")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = list(WorkerProfile.REGISTRATION_DESIGNATIONS)
        if self.instance and self.instance.pk and self.instance.designation == WorkerProfile.Designation.CREW_LEADER:
            choices.append((WorkerProfile.Designation.CREW_LEADER, "Crew Leader (Legacy)"))
        self.fields["designation"].choices = choices
        if self.instance and self.instance.user:
            self.fields["full_name"].initial = self.instance.user.get_full_name() or self.instance.user.username
            self.fields["email"].initial = self.instance.user.email
            self.fields["phone"].initial = self.instance.phone or self.instance.user.phone

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        first_name, _, last_name = self.cleaned_data["full_name"].strip().partition(" ")
        user.first_name = first_name
        user.last_name = last_name
        user.email = self.cleaned_data["email"]
        user.phone = self.cleaned_data["phone"]
        user.save()
        profile.phone = self.cleaned_data["phone"]
        if commit:
            profile.save()
        return profile


class OTPRequestForm(forms.Form):
    email = forms.EmailField(label="Email Address", widget=forms.EmailInput(attrs={"autocomplete": "email"}))


class OTPVerifyForm(forms.Form):
    email = forms.EmailField(widget=forms.HiddenInput)
    otp = forms.CharField(max_length=6, label="One-Time Passcode", widget=forms.TextInput(attrs={"placeholder": "123456"}))
    password = forms.CharField(label="New Password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    password_confirm = forms.CharField(label="Confirm New Password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "The passwords do not match.")
        return cleaned_data
