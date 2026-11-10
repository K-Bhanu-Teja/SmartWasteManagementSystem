import tempfile

from django.core.files.base import ContentFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import DriverProfile, User, WorkerProfile
from citizen_services.models import Complaint
from .models import Attendance, Crew, CrewAssignment, DriverVehicleAssignment, TaskStatusHistory, Vehicle, WorkerLocation


class CrewWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="municipal-admin",
            email="admin@example.test",
            password="StrongPassword123!",
            role=User.Role.ADMINISTRATOR,
        )
        self.client.force_login(self.admin)
        self.vehicle = Vehicle.objects.create(identifier="TRUCK-2", registration_number="XYZ-789")
        self.driver = User.objects.create_user(
            username="driver-two",
            email="driver2@example.test",
            password="StrongPassword123!",
            role=User.Role.DRIVER,
            approved=True,
        )
        self.leader = User.objects.create_user(
            username="leader-two",
            email="leader2@example.test",
            password="StrongPassword123!",
            role=User.Role.CREW_LEADER,
            approved=True,
        )
        self.cleaner = User.objects.create_user(
            username="cleaner-two",
            email="cleaner2@example.test",
            password="StrongPassword123!",
            role=User.Role.CLEANER,
            approved=True,
        )

    def crew_data(self):
        return {
            "name": "Evening crew",
            "drivers": [self.driver.pk],
            "workers": [self.leader.pk, self.cleaner.pk],
            "vehicles": [self.vehicle.pk],
            "crew_leader": self.leader.pk,
        }

    def test_admin_can_assign_change_and_remove_driver_vehicle(self):
        replacement_vehicle = Vehicle.objects.create(
            identifier="TRUCK-3",
            registration_number="LMN-456",
            vehicle_type="Compactor",
        )

        assigned = self.client.post(reverse("operations:assign_vehicle"), {
            "driver_id": self.driver.pk,
            "vehicle_id": self.vehicle.pk,
        })
        self.assertRedirects(assigned, reverse("operations:worker_management"))
        assignment = DriverVehicleAssignment.objects.get(driver=self.driver, is_active=True)
        self.assertEqual(assignment.vehicle, self.vehicle)
        self.vehicle.refresh_from_db()
        self.assertFalse(self.vehicle.is_available)
        other_driver = User.objects.create_user(
            username="other-approved-driver",
            email="other-approved-driver@example.test",
            password="StrongPassword123!",
            role=User.Role.DRIVER,
            approved=True,
        )
        blocked = self.client.post(reverse("operations:assign_vehicle"), {
            "driver_id": other_driver.pk,
            "vehicle_id": self.vehicle.pk,
        })
        self.assertRedirects(blocked, reverse("operations:worker_management"))
        self.assertFalse(DriverVehicleAssignment.objects.filter(driver=other_driver, is_active=True).exists())

        changed = self.client.post(reverse("operations:assign_vehicle"), {
            "driver_id": self.driver.pk,
            "vehicle_id": replacement_vehicle.pk,
        })
        self.assertRedirects(changed, reverse("operations:worker_management"))
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertIsNotNone(assignment.released_at)
        self.assertTrue(DriverVehicleAssignment.objects.filter(
            driver=self.driver,
            vehicle=replacement_vehicle,
            is_active=True,
        ).exists())
        self.vehicle.refresh_from_db()
        replacement_vehicle.refresh_from_db()
        self.assertTrue(self.vehicle.is_available)
        self.assertFalse(replacement_vehicle.is_available)

        removed = self.client.post(reverse("operations:remove_vehicle_assignment", args=[self.driver.pk]))
        self.assertRedirects(removed, reverse("operations:worker_management"))
        self.assertFalse(DriverVehicleAssignment.objects.filter(driver=self.driver, is_active=True).exists())
        replacement_vehicle.refresh_from_db()
        self.assertTrue(replacement_vehicle.is_available)

    def test_unapproved_driver_cannot_be_assigned_a_vehicle(self):
        pending_driver = User.objects.create_user(
            username="pending-vehicle-driver",
            email="pending-vehicle-driver@example.test",
            password="StrongPassword123!",
            role=User.Role.DRIVER,
            approved=False,
        )

        response = self.client.post(reverse("operations:assign_vehicle"), {
            "driver_id": pending_driver.pk,
            "vehicle_id": self.vehicle.pk,
        })

        self.assertEqual(response.status_code, 404)
        self.assertFalse(DriverVehicleAssignment.objects.filter(driver=pending_driver).exists())
        self.vehicle.refresh_from_db()
        self.assertTrue(self.vehicle.is_available)

    def test_admin_page_lists_available_vehicle_and_driver_assignment(self):
        response = self.client.get(reverse("operations:worker_management"))

        self.assertContains(response, "Driver vehicle assignments")
        self.assertContains(response, self.driver.email)
        self.assertContains(response, self.vehicle.registration_number)
        self.assertContains(response, 'name="driver_id"')
        self.assertContains(response, 'name="vehicle_id"')
        self.assertContains(response, "Available vehicles")
        self.assertContains(response, "Currently assigned vehicles")
        self.assertContains(response, "Vehicle type")

    def test_pending_applications_show_driver_and_worker_details(self):
        driver = User.objects.create_user(
            username="pending-driver",
            email="pending-driver@example.test",
            password="StrongPassword123!",
            first_name="Priya",
            last_name="Driver",
            phone="9876543210",
            role=User.Role.DRIVER,
            approved=False,
        )
        DriverProfile.objects.create(
            user=driver,
            date_of_birth="1990-01-02",
            gender=DriverProfile.Gender.WOMAN,
            residential_address="12 Driver Street",
            licence_number="DL-ADMIN-123",
            licence_expiry_date="2030-01-02",
            experience_years=8,
            licence_document="driver_licences/licence.pdf",
        )
        worker = User.objects.create_user(
            username="pending-cleaner",
            email="pending-worker@example.test",
            password="StrongPassword123!",
            first_name="Ravi",
            last_name="Worker",
            role=User.Role.CLEANER,
            approved=False,
        )
        WorkerProfile.objects.create(
            user=worker,
            date_of_birth="1992-03-04",
            residential_address="8 Worker Road",
            village_name="North Village",
            ward_number="7",
            experience_years=3,
        )

        response = self.client.get(reverse("operations:worker_management"))

        self.assertContains(response, "Priya Driver")
        self.assertContains(response, "12 Driver Street")
        self.assertContains(response, "DL-ADMIN-123")
        self.assertContains(response, reverse("operations:worker_registration_document", args=[driver.pk]))
        self.assertContains(response, "Ravi Worker")
        self.assertContains(response, "8 Worker Road")
        self.assertContains(response, "North Village")

    def test_admin_can_download_driver_document(self):
        with tempfile.TemporaryDirectory() as upload_dir, override_settings(MEDIA_ROOT=upload_dir):
            driver = User.objects.create_user(
                username="document-driver",
                email="document-driver@example.test",
                password="StrongPassword123!",
                role=User.Role.DRIVER,
                approved=False,
            )
            DriverProfile.objects.create(
                user=driver,
                date_of_birth="1990-01-02",
                residential_address="12 Driver Street",
                licence_number="DL-DOCUMENT-123",
                licence_expiry_date="2030-01-02",
                experience_years=8,
                licence_document=ContentFile(b"%PDF-1.4 test", name="licence.pdf"),
            )

            response = self.client.get(reverse("operations:worker_registration_document", args=[driver.pk]))

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Disposition"], 'inline; filename="licence.pdf"')
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4 test")

    def test_non_admin_cannot_download_registration_document(self):
        self.client.force_login(self.driver)

        response = self.client.get(reverse("operations:worker_registration_document", args=[self.driver.pk]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:dashboard"))

    def test_admin_can_reject_pending_worker(self):
        worker = User.objects.create_user(
            username="pending-to-reject",
            email="pending-to-reject@example.test",
            password="StrongPassword123!",
            role=User.Role.CLEANER,
            approved=False,
        )

        response = self.client.post(reverse("operations:reject_worker", args=[worker.pk]))

        self.assertRedirects(response, reverse("operations:worker_management"))
        worker.refresh_from_db()
        self.assertTrue(worker.rejected)
        self.assertFalse(worker.approved)
        self.assertFalse(worker.is_active)
        queue = self.client.get(reverse("operations:worker_management"))
        self.assertNotContains(queue, worker.email)

    def test_create_and_dissolve_crew_releases_vehicle_and_people(self):
        response = self.client.post(reverse("operations:create_crew"), self.crew_data())
        self.assertRedirects(response, reverse("operations:worker_management"))
        crew = Crew.objects.get(name="Evening crew", is_active=True)
        self.vehicle.refresh_from_db()
        self.assertFalse(self.vehicle.is_available)

        response = self.client.post(reverse("operations:dissolve_crew", args=[crew.pk]))
        self.assertRedirects(response, reverse("operations:worker_management"))
        crew.refresh_from_db()
        self.vehicle.refresh_from_db()
        self.assertFalse(crew.is_active)
        self.assertFalse(self.vehicle.is_available)
        self.assertTrue(DriverVehicleAssignment.objects.filter(driver=self.driver, vehicle=self.vehicle, is_active=True).exists())

    def test_selected_crew_leader_must_also_be_selected_as_a_worker(self):
        data = self.crew_data()
        data["workers"] = [self.cleaner.pk]

        response = self.client.post(reverse("operations:create_crew"), data)

        self.assertRedirects(response, reverse("operations:worker_management"))
        self.assertFalse(Crew.objects.filter(name="Evening crew").exists())

    def test_unapproved_workers_cannot_create_a_crew(self):
        self.driver.approved = False
        self.driver.is_active = False
        self.driver.save()

        response = self.client.post(reverse("operations:create_crew"), self.crew_data())

        self.assertRedirects(response, reverse("operations:worker_management"))
        self.assertFalse(Crew.objects.filter(is_active=True).exists())

    def test_worker_recommendations_use_distance_and_availability(self):
        self.driver.last_latitude = 16.833944
        self.driver.last_longitude = 81.531444
        self.driver.save(update_fields=["last_latitude", "last_longitude"])
        WorkerLocation.objects.create(
            user=self.driver,
            latitude="16.833944",
            longitude="81.531444",
            is_signed_in=True,
            availability=WorkerLocation.Availability.AVAILABLE,
        )

        response = self.client.get(reverse("operations:worker_management"), {
            "latitude": "16.833944",
            "longitude": "81.531444",
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "driver-two")
        self.assertContains(response, "Available")

    def test_admin_complaint_map_api_returns_status_and_coordinates(self):
        citizen = User.objects.create_user(
            username="map-complainant",
            email="map-complainant@example.test",
            password="StrongPassword123!",
        )
        complaint = Complaint.objects.create(
            citizen=citizen,
            category=Complaint.Category.OVERFLOWING_BIN,
            description="Overflowing bin near the park.",
            photo="",
            latitude="16.833944",
            longitude="81.531444",
            status=Complaint.Status.PENDING,
        )

        response = self.client.get(reverse("operations:complaints_map_api"))

        self.assertEqual(response.status_code, 200)
        marker = response.json()["complaints"][0]
        self.assertEqual(marker["id"], complaint.pk)
        self.assertEqual(marker["status"], Complaint.Status.PENDING)
        self.assertEqual(marker["latitude"], 16.833944)
        dashboard = self.client.get(reverse("operations:admin_dashboard"))
        self.assertContains(dashboard, reverse("operations:complaints_map_api"))
        self.assertContains(dashboard, 'data-marker-filter="complaint:pending"')

    def test_non_admin_cannot_read_complaint_map_api(self):
        self.client.force_login(self.driver)

        response = self.client.get(reverse("operations:complaints_map_api"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:dashboard"))

    def test_complaint_management_can_assign_a_status(self):
        citizen = User.objects.create_user(
            username="complainant",
            email="complainant@example.test",
            password="StrongPassword123!",
        )
        complaint = Complaint.objects.create(
            citizen=citizen,
            category=Complaint.Category.MISSED_COLLECTION,
            description="Collection was missed.",
            photo="",
            latitude="16.833944",
            longitude="81.531444",
        )

        self.client.post(reverse("operations:create_crew"), self.crew_data())
        crew = Crew.objects.get(name="Evening crew", is_active=True)
        complaint_page = self.client.get(reverse("operations:complaint_management"))
        self.assertContains(complaint_page, "Allocate an existing crew")
        self.assertContains(complaint_page, f'<option value="{crew.pk}">Evening crew')

        response = self.client.post(
            reverse("operations:assign_task", args=["COMPLAINT", complaint.pk]),
            {"crew_id": crew.pk},
        )

        self.assertRedirects(response, reverse("operations:complaint_management"))
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, Complaint.Status.ASSIGNED)
        self.assertEqual(complaint.assigned_crew, crew)
        self.assertTrue(CrewAssignment.objects.filter(complaint=complaint, status=CrewAssignment.Status.ACTIVE).exists())
        self.assertEqual(TaskStatusHistory.objects.filter(complaint=complaint).count(), 1)

    def test_complaint_assign_and_cancel_forms_pass_csrf_validation(self):
        citizen = User.objects.create_user(username="csrf-citizen", email="csrf-citizen@example.test", password="test-pass")
        complaint = Complaint.objects.create(
            citizen=citizen,
            category=Complaint.Category.MISSED_COLLECTION,
            description="Collection was missed.",
            photo="",
            latitude="16.833944",
            longitude="81.531444",
        )
        self.client.post(reverse("operations:create_crew"), self.crew_data())
        crew = Crew.objects.get(name="Evening crew", is_active=True)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        page = csrf_client.get(reverse("operations:complaint_management"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, complaint.description)
        self.assertIn("csrftoken", csrf_client.cookies)
        self.assertGreaterEqual(page.content.count(b'name="csrfmiddlewaretoken"'), 3)
        csrf_token = csrf_client.cookies["csrftoken"].value

        assigned = csrf_client.post(
            reverse("operations:assign_task", args=["COMPLAINT", complaint.pk]),
            {"crew_id": crew.pk, "csrfmiddlewaretoken": csrf_token},
        )
        self.assertEqual(assigned.status_code, 302)
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, Complaint.Status.ASSIGNED)

        cancelled = csrf_client.post(
            reverse("operations:cancel_task", args=["COMPLAINT", complaint.pk]),
            {"remarks": "Cancelled by administrator.", "csrfmiddlewaretoken": csrf_token},
        )
        self.assertEqual(cancelled.status_code, 302)
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, Complaint.Status.CANCELLED)


class AttendanceWorkflowTests(TestCase):
    def setUp(self):
        self.worker = User.objects.create_user(
            username="verified-driver",
            email="verified-driver@example.test",
            password="StrongPassword123!",
            role=User.Role.DRIVER,
            approved=True,
        )
        self.client.force_login(self.worker)

    def test_attendance_is_rejected_outside_office_radius(self):
        response = self.client.post(reverse("operations:check_in"), {
            "latitude": "17.0",
            "longitude": "82.0",
        })

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Attendance.objects.filter(worker=self.worker).exists())

    def test_attendance_is_saved_inside_office_radius(self):
        response = self.client.post(reverse("operations:check_in"), {
            "latitude": "16.833944",
            "longitude": "81.531444",
        })

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Attendance.objects.filter(worker=self.worker).exists())
