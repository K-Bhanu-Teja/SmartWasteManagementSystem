import re
import tempfile
from datetime import timedelta

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import CitizenRegistrationForm, DriverRegistrationForm
from .models import CitizenProfile, DriverProfile, User, WorkerProfile


class AccountWorkflowTests(TestCase):
    @override_settings(DEVELOPMENT_SERVER_SESSION_RESET=True)
    def test_development_server_restart_logs_out_existing_session(self):
        administrator = User.objects.create_user(
            username="restart-admin",
            email="restart-admin@example.test",
            password="AdminPassword123!",
            role=User.Role.ADMINISTRATOR,
        )
        self.client.force_login(administrator)
        session = self.client.session
        session["_development_server_instance"] = "previous-server-process"
        session.save()

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertContains(response, reverse("accounts:login"))
        self.assertNotContains(response, "Sign out")
        self.assertNotContains(response, "restart-admin")

    def test_citizen_login_redirects_to_citizen_dashboard(self):
        User.objects.create_user(
            username="citizen",
            email="citizen@example.test",
            password="StrongPassword123!",
            role=User.Role.CITIZEN,
        )

        response = self.client.post(reverse("accounts:login"), {
            "username": "citizen@example.test",
            "password": "StrongPassword123!",
        })

        self.assertRedirects(response, reverse("citizen:dashboard"))

    def test_pending_workers_get_approval_message_but_cannot_login(self):
        for role, email, password in (
            (User.Role.DRIVER, "pending.driver@example.test", "DriverPassword123!"),
            (User.Role.CLEANER, "pending.worker@example.test", "WorkerPassword123!"),
        ):
            User.objects.create_user(
                username=email,
                email=email,
                password=password,
                role=role,
                approved=False,
                is_active=False,
            )

            response = self.client.post(reverse("accounts:login"), {
                "username": email,
                "password": password,
            })

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f"Your {'driver' if role == User.Role.DRIVER else 'worker'} account is awaiting administrator approval.")
            self.assertFalse(response.wsgi_request.user.is_authenticated)

            wrong_password_response = self.client.post(reverse("accounts:login"), {
                "username": email,
                "password": "WrongPassword123!",
            })
            self.assertNotContains(wrong_password_response, "awaiting administrator approval")

    def test_rejected_worker_gets_rejection_notice_but_cannot_login(self):
        User.objects.create_user(
            username="rejected-driver",
            email="rejected.driver@example.test",
            password="DriverPassword123!",
            role=User.Role.DRIVER,
            approved=False,
            rejected=True,
        )

        response = self.client.post(reverse("accounts:login"), {
            "username": "rejected.driver@example.test",
            "password": "DriverPassword123!",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your driver application was rejected.")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_home_and_registration_urls_use_unified_form(self):
        home = self.client.get(reverse("home"))
        self.assertContains(home, reverse("accounts:login"))
        self.assertContains(home, reverse("accounts:register"))
        self.assertContains(home, "Waste collection that works")
        self.assertNotContains(home, "Open complaint management")
        self.assertNotContains(home, "Map filters")
        self.assertNotContains(home, "Add public dustbin")
        self.assertNotContains(home, "data-complaints-url=")
        admin_page = self.client.get(reverse("operations:admin_dashboard"))
        self.assertRedirects(
            admin_page,
            f"{reverse('accounts:login')}?next={reverse('operations:admin_dashboard')}",
        )
        administrator = User.objects.create_user(
            username="home-admin",
            email="home-admin@example.test",
            password="AdminPassword123!",
            role=User.Role.ADMINISTRATOR,
        )
        self.client.force_login(administrator)
        admin_home = self.client.get(reverse("home"))
        self.assertContains(admin_home, "Waste collection that works")
        self.assertNotContains(admin_home, "Map and service area")
        self.assertNotContains(admin_home, "Map filters")
        self.assertNotContains(admin_home, "Add public dustbin")
        self.assertNotContains(admin_home, "data-complaints-url=")
        for route_name in ("register_citizen", "register_driver", "register_worker"):
            path = reverse(f"accounts:{route_name}")
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "auth-card-wide")
            self.assertContains(response, 'id="registration-role"')
            self.assertContains(response, 'data-role-section="citizen"')
            self.assertContains(response, 'data-role-section="driver"')
            self.assertContains(response, 'data-role-section="worker"')
            self.assertContains(response, 'class="form-stack registration-fields"', count=4)
            self.assertContains(response, 'aria-label="Show password"', count=2)
            self.assertNotContains(response, "Vehicle Type")
            self.assertNotContains(response, "Vehicle Registration Number")
        login_page = self.client.get(reverse("accounts:login"))
        self.assertEqual(login_page.status_code, 200)
        self.assertNotContains(login_page, "Remember me")
        self.assertContains(login_page, 'class="password-toggle"')
        self.assertContains(login_page, 'class="password-icon password-icon-eye"')
        self.assertEqual(self.client.get(reverse("accounts:register")).status_code, 200)
        legacy_register = self.client.get(reverse("legacy_register"))
        self.assertEqual(legacy_register.status_code, 200)
        self.assertContains(legacy_register, 'id="registration-role"')
        self.assertEqual(self.client.get(reverse("accounts:password_reset")).status_code, 200)

    def test_citizen_registration_creates_active_profile_and_logs_in(self):
        response = self.client.post(reverse("accounts:register_citizen"), {
            "role": "citizen",
            "full_name": "Mira Patel",
            "email": "mira@example.test",
            "mobile_number": "9876543210",
            "password": "CitizenStrongPassword123!",
            "password_confirm": "CitizenStrongPassword123!",
            "house_number": "12A",
            "street_locality": "Lake Road",
            "ward_number": "4",
            "village_name": "Greenfield",
        })

        self.assertRedirects(response, reverse("citizen:dashboard"))
        user = User.objects.get(email="mira@example.test")
        self.assertTrue(user.is_active)
        self.assertTrue(user.approved)
        self.assertEqual(user.get_full_name(), "Mira Patel")
        self.assertEqual(user.citizen_profile, CitizenProfile.objects.get(user=user))
        self.assertTrue(user.check_password("CitizenStrongPassword123!"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_driver_registration_uploads_licence_and_remains_pending(self):
        with tempfile.TemporaryDirectory() as upload_dir, override_settings(MEDIA_ROOT=upload_dir):
            response = self.client.post(reverse("accounts:register_driver"), {
                "role": "driver",
                "full_name": "Dev Kumar",
                "email": "dev.driver@example.test",
                "mobile_number": "+919876543210",
                "password": "DriverStrongPassword123!",
                "password_confirm": "DriverStrongPassword123!",
                "date_of_birth": "1990-01-01",
                "gender": "man",
                "residential_address": "14 Hill Street",
                "licence_number": "DL-TEST-100",
                "licence_expiry_date": (timezone.localdate() + timedelta(days=365)).isoformat(),
                "experience_years": "6",
                "licence_document": SimpleUploadedFile("licence.pdf", b"%PDF-1.4 test", content_type="application/pdf"),
            })

            self.assertRedirects(response, reverse("accounts:login"))
            driver = User.objects.get(email="dev.driver@example.test")
            self.assertEqual(driver.role, User.Role.DRIVER)
            self.assertFalse(driver.approved)
            self.assertFalse(driver.is_active)
            profile = DriverProfile.objects.get(user=driver)
            self.assertTrue(profile.licence_document.name.endswith("licence.pdf"))
            denied = self.client.post(reverse("accounts:login"), {
                "username": driver.email,
                "password": "DriverStrongPassword123!",
            })
            self.assertEqual(denied.status_code, 200)
            self.assertFalse(denied.wsgi_request.user.is_authenticated)

    def test_worker_registration_is_pending_and_optional_document_is_blank(self):
        response = self.client.post(reverse("accounts:register_worker"), {
            "role": "worker",
            "full_name": "Ravi Das",
            "email": "ravi.worker@example.test",
            "mobile_number": "9876543211",
            "password": "WorkerStrongPassword123!",
            "password_confirm": "WorkerStrongPassword123!",
            "date_of_birth": "1992-02-02",
            "residential_address": "8 Market Lane",
            "village_name": "North Village",
            "ward_number": "7",
            "experience_years": "2",
        })

        self.assertRedirects(response, reverse("accounts:login"))
        worker = User.objects.get(email="ravi.worker@example.test")
        self.assertEqual(worker.role, User.Role.CLEANER)
        self.assertFalse(worker.approved)
        self.assertFalse(worker.is_active)
        self.assertEqual(WorkerProfile.objects.get(user=worker).identification_document.name, "")

    def test_registration_rejects_invalid_mobile_password_and_driver_document(self):
        form = DriverRegistrationForm(data={
            "full_name": "Test Driver",
            "email": "form.driver@example.test",
            "mobile_number": "12345",
            "password": "Password123!",
            "password_confirm": "not-the-same",
            "date_of_birth": "1990-01-01",
            "residential_address": "1 Test Road",
            "licence_number": "DL-INVALID",
            "licence_expiry_date": (timezone.localdate() + timedelta(days=365)).isoformat(),
            "experience_years": "1",
        }, files={
            "licence_document": SimpleUploadedFile("licence.pdf", b"not a pdf", content_type="application/pdf"),
        })
        self.assertFalse(form.is_valid())
        self.assertIn("mobile_number", form.errors)
        self.assertIn("password_confirm", form.errors)
        self.assertIn("licence_document", form.errors)

    def test_driver_registration_rejects_duplicate_licence_number(self):
        existing_user = User.objects.create_user(
            username="existing-driver",
            email="existing.driver@example.test",
            password="StrongPassword123!",
            role=User.Role.DRIVER,
        )
        DriverProfile.objects.create(
            user=existing_user,
            date_of_birth="1990-01-01",
            residential_address="1 Existing Road",
            licence_number="DL-DUPLICATE",
            licence_expiry_date="2030-01-01",
            experience_years=5,
            licence_document="existing.pdf",
        )
        form = DriverRegistrationForm(data={"licence_number": "dl-duplicate"})

        self.assertFalse(form.is_valid())
        self.assertIn("licence_number", form.errors)

    def test_login_uses_standard_session_timeout(self):
        User.objects.create_user(
            username="standard-timeout",
            email="remember@example.test",
            password="StrongPassword123!",
        )
        self.client.post(reverse("accounts:login"), {
            "username": "remember@example.test",
            "password": "StrongPassword123!",
        })
        self.client.get(reverse("citizen:dashboard"))

        self.assertEqual(self.client.session.get_expiry_age(), 30 * 60)

    def test_approved_driver_and_worker_can_use_common_login(self):
        for role, email in (
            (User.Role.DRIVER, "approved.driver@example.test"),
            (User.Role.CLEANER, "approved.worker@example.test"),
            (User.Role.CREW_LEADER, "approved.leader@example.test"),
            (User.Role.ADMINISTRATOR, "approved.admin@example.test"),
        ):
            User.objects.create_user(
                username=email,
                email=email,
                password="StrongPassword123!",
                role=role,
                approved=True,
                is_active=True,
            )
            response = self.client.post(reverse("accounts:login"), {
                "username": email,
                "password": "StrongPassword123!",
            })
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.wsgi_request.user.is_authenticated)
            self.client.logout()

    def test_registration_rejects_email_duplicates_case_insensitively(self):
        User.objects.create_user(
            username="existing",
            email="resident@example.test",
            password="StrongPassword123!",
        )
        form = CitizenRegistrationForm(data={
            "full_name": "New Resident",
            "email": "RESIDENT@example.test",
            "mobile_number": "9876543210",
            "password": "CitizenStrongPassword123!",
            "password_confirm": "CitizenStrongPassword123!",
            "house_number": "1",
            "street_locality": "Main Street",
            "ward_number": "1",
            "village_name": "Greenfield",
        })

        self.assertFalse(form.is_valid())
        self.assertIn("email", form.errors)

    def test_password_reset_uses_one_time_code(self):
        user = User.objects.create_user(
            username="recover-me",
            email="recover@example.test",
            password="OriginalPassword123!",
        )
        response = self.client.post(reverse("accounts:password_reset"), {"email": user.email})
        self.assertRedirects(response, reverse("accounts:password_reset_verify"))
        self.assertEqual(len(mail.outbox), 1)
        code = re.search(r"one-time password is (\d{6})", mail.outbox[0].body).group(1)

        response = self.client.post(reverse("accounts:password_reset_verify"), {
            "email": user.email,
            "code": code,
            "new_password": "ReplacementPassword123!",
        })

        self.assertRedirects(response, reverse("accounts:login"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("ReplacementPassword123!"))
