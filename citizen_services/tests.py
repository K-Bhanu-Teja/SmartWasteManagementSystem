from datetime import timedelta
from io import BytesIO
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import User
from workforce.models import Crew, Vehicle

from .models import Complaint, Dustbin, PickupRequest, SavedLocation, ServiceBoundary


class CitizenServiceTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        media_settings = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.citizen = User.objects.create_user(
            username="resident",
            email="resident@example.test",
            password="StrongPassword123!",
        )
        self.client.force_login(self.citizen)

    def test_citizen_can_submit_and_track_complaint(self):
        image = Image.new("RGB", (2, 2), color="green")
        image_data = BytesIO()
        image.save(image_data, format="PNG")
        response = self.client.post(reverse("citizen:create_complaint"), {
            "category": Complaint.Category.OVERFLOWING_BIN,
            "description": "The public bin is full.",
            "latitude": "16.833944",
            "longitude": "81.531444",
            "photo": SimpleUploadedFile("bin.png", image_data.getvalue(), content_type="image/png"),
        })

        self.assertRedirects(response, reverse("citizen:complaints"))
        complaint = Complaint.objects.get(citizen=self.citizen)
        self.assertEqual(complaint.status, Complaint.Status.PENDING)
        self.assertTrue(complaint.photo)
        complaint_page = self.client.get(reverse("citizen:complaints"))
        self.assertContains(complaint_page, "Pending")
        self.assertContains(complaint_page, "The public bin is full.")

    def test_citizen_can_schedule_a_future_pickup(self):
        future_time = (timezone.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(reverse("citizen:create_pickup"), {
            "address": "12 Green Street",
            "category": PickupRequest.Category.HOUSEHOLD,
            "quantity": "2",
            "scheduled_at": future_time,
            "latitude": "16.833944",
            "longitude": "81.531444",
        })

        self.assertRedirects(response, reverse("citizen:pickups"))
        pickup = PickupRequest.objects.get(citizen=self.citizen)
        self.assertEqual(pickup.status, PickupRequest.Status.PENDING)
        pickup_page = self.client.get(reverse("citizen:pickups"))
        self.assertContains(pickup_page, "Pickup tracking")
        self.assertContains(pickup_page, "Details / location")
        self.assertContains(pickup_page, "Submitted / updated")
        self.assertContains(pickup_page, pickup.address)
        self.assertContains(pickup_page, pickup.get_category_display())
        self.assertContains(pickup_page, pickup.get_status_display())
        self.assertContains(pickup_page, "Scheduled")

    def test_dustbin_api_returns_active_map_assets(self):
        Dustbin.objects.create(
            name="Central Market",
            category=Dustbin.Category.PUBLIC_DUSTBIN,
            latitude="16.833944",
            longitude="81.531444",
        )
        response = self.client.get(reverse("citizen:dustbins_api"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["dustbins"][0]["name"], f"DBno{Dustbin.objects.get().pk}")
        self.assertEqual(response.json()["dustbins"][0]["category"], Dustbin.Category.PUBLIC_DUSTBIN)

    def test_dustbin_api_only_exposes_locations_inside_service_boundary(self):
        ServiceBoundary.objects.create(
            points=[
                {"lat": 16.8, "lng": 81.5},
                {"lat": 16.9, "lng": 81.5},
                {"lat": 16.9, "lng": 81.6},
                {"lat": 16.8, "lng": 81.6},
            ],
            created_by=self.citizen,
        )
        Dustbin.objects.create(
            name="Inside",
            category=Dustbin.Category.PUBLIC_DUSTBIN,
            latitude="16.85",
            longitude="81.55",
        )
        Dustbin.objects.create(
            name="Outside",
            category=Dustbin.Category.PUBLIC_DUSTBIN,
            latitude="17.0",
            longitude="82.0",
        )

        response = self.client.get(reverse("citizen:dustbins_api"))

        dustbins = response.json()["dustbins"]
        self.assertEqual(
            [item["name"] for item in dustbins],
            [f"DBno{dustbins[0]['id']}"],
        )

    def test_dashboard_links_to_separate_services_without_forms(self):
        response = self.client.get(reverse("citizen:dashboard"))

        self.assertContains(response, reverse("citizen:complaints"))
        self.assertContains(response, reverse("citizen:pickups"))
        self.assertNotContains(response, "Submit a complaint")
        self.assertNotContains(response, "Schedule home pickup")
        self.assertNotContains(response, "Add map marker")
        self.assertNotContains(response, "data-complaints-url")
        self.assertNotContains(response, "data-marker-filter")

    def test_complaint_and_pickup_pages_are_separate(self):
        complaints = self.client.get(reverse("citizen:complaints"))
        pickups = self.client.get(reverse("citizen:pickups"))

        self.assertContains(complaints, "Complaint tracking")
        self.assertNotContains(complaints, "Pickup requests")
        self.assertContains(pickups, "Schedule a home pickup")
        self.assertContains(pickups, "Pickup tracking")
        self.assertNotContains(pickups, "Complaint tracking")

    @override_settings(VEHICLE_ALERT_RADIUS_METERS=1000)
    def test_vehicle_alert_uses_saved_location(self):
        SavedLocation.objects.create(
            citizen=self.citizen,
            label="Home",
            latitude="16.833944",
            longitude="81.531444",
        )
        vehicle = Vehicle.objects.create(
            identifier="TRUCK-1",
            registration_number="ABC-123",
            latitude="16.833944",
            longitude="81.531444",
        )
        driver = User.objects.create_user(
            username="driver",
            email="driver@example.test",
            password="StrongPassword123!",
            role=User.Role.DRIVER,
            approved=True,
        )
        leader = User.objects.create_user(
            username="leader",
            email="leader@example.test",
            password="StrongPassword123!",
            role=User.Role.CREW_LEADER,
            approved=True,
        )
        cleaner = User.objects.create_user(
            username="cleaner",
            email="cleaner@example.test",
            password="StrongPassword123!",
            role=User.Role.CLEANER,
            approved=True,
        )
        crew = Crew.objects.create(name="North crew", vehicle=vehicle, driver=driver, crew_leader=leader)
        crew.cleaners.add(cleaner)

        response = self.client.get(reverse("citizen:vehicle_alerts_api"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["alerts"][0]["vehicle"], "TRUCK-1")
