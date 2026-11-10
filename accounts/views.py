import secrets
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.utils import timezone

from .forms import (
    CitizenRegistrationForm,
    EmailAuthenticationForm,
    OTPRequestForm,
    OTPVerifyForm,
)
from .models import PasswordResetOTP, User


def login_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = EmailAuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["username"]
        user = authenticate(request, username=email, password=form.cleaned_data["password"])
        if user is not None:
            login(request, user)
            if user.role == User.Role.ADMINISTRATOR or user.is_superuser:
                return redirect("operations:admin_dashboard")
            if user.role == User.Role.WORKER:
                return redirect("operations:worker_dashboard")
            return redirect("citizen:dashboard")
        messages.error(request, "Account is not approved yet or credentials are incorrect.")
    return render(request, "accounts/login.html", {"form": form})


def register_view(request):
    """Citizen registration view. Only citizens can self-register."""
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = CitizenRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="accounts.backends.EmailBackend")
        messages.success(request, "Your citizen account has been successfully created!")
        return redirect("citizen:dashboard")

    return render(request, "accounts/register.html", {"form": form})


def logout_view(request):
    logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("home")


@login_required
def dashboard(request):
    """Central router to redirect authenticated user to role-specific dashboard."""
    if request.user.role == User.Role.ADMINISTRATOR or request.user.is_superuser:
        return redirect("operations:admin_dashboard")
    if request.user.role == User.Role.WORKER:
        return redirect("operations:worker_dashboard")
    return redirect("citizen:dashboard")


def password_reset_request(request):
    form = OTPRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        user = User.objects.filter(email__iexact=email).first()
        if user:
            otp = f"{secrets.randbelow(900000) + 100000:06d}"
            PasswordResetOTP.objects.create(
                user=user,
                code_hash=make_password(otp),
                expires_at=timezone.now() + timedelta(minutes=15),
            )
            # Send simulated email / log
            send_mail(
                "SWMS Password Reset Passcode",
                f"Your SWMS reset passcode is {otp}. It expires in 15 minutes.",
                None,
                [user.email],
                fail_silently=True,
            )
            request.session["reset_email"] = user.email
            messages.info(request, f"A 6-digit passcode has been sent to {user.email}.")
            return redirect("accounts:password_reset_verify")
        messages.error(request, "No account was found with that email address.")
    return render(request, "accounts/password_reset.html", {"form": form})


def password_reset_verify(request):
    email = request.session.get("reset_email")
    if not email:
        return redirect("accounts:password_reset")

    form = OTPVerifyForm(request.POST or None, initial={"email": email})
    if request.method == "POST" and form.is_valid():
        user = User.objects.filter(email__iexact=email).first()
        otp_attempt = form.cleaned_data["otp"].strip()
        record = PasswordResetOTP.objects.filter(
            user=user,
            used_at__isnull=True,
            expires_at__gte=timezone.now(),
        ).first()

        if record and check_password(otp_attempt, record.code_hash):
            record.used_at = timezone.now()
            record.save(update_fields=["used_at"])
            user.set_password(form.cleaned_data["password"])
            user.save(update_fields=["password"])
            request.session.pop("reset_email", None)
            messages.success(request, "Password updated successfully. You can now sign in.")
            return redirect("accounts:login")
        messages.error(request, "Invalid or expired passcode.")

    return render(request, "accounts/password_reset_verify.html", {"form": form, "email": email})
