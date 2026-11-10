from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.models import User
from citizen_services.models import Complaint, Dustbin, ServiceBoundary
from workforce.views import _distance_meters, _valid_coordinates


class RoleAndLocationTests(SimpleTestCase):
    def test_all_required_roles_are_defined(self):
        self.assertEqual(
            {choice for choice, _label in User.Role.choices},
            {"visitor", "citizen", "driver", "cleaner", "crew_leader", "administrator"},
        )

    def test_complaint_lifecycle_contains_all_required_states(self):
        self.assertEqual(
            {choice for choice, _label in Complaint.Status.choices},
            {
                "pending",
                "assigned",
                "crew_on_the_way",
                "arrived",
                "in_progress",
                "completed_awaiting_confirmation",
                "confirmed",
                "completed",
                "closed",
                "admin_review",
                "rejected_disputed",
                "cancelled",
            },
        )

    def test_distance_between_same_coordinates_is_zero(self):
        self.assertEqual(_distance_meters(16.8, 81.5, 16.8, 81.5), 0)

    def test_coordinate_validation_rejects_invalid_and_non_finite_values(self):
        self.assertTrue(_valid_coordinates(16.8, 81.5))
        self.assertFalse(_valid_coordinates(91, 0))
        self.assertFalse(_valid_coordinates(0, float("nan")))


class ServiceBoundaryManagementTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="mapadmin",
            email="mapadmin@example.test",
            password="test-password-123",
            role=User.Role.ADMINISTRATOR,
        )
        self.citizen = User.objects.create_user(
            username="mapcitizen",
            email="mapcitizen@example.test",
            password="test-password-123",
        )

    def test_administrator_can_save_and_replace_four_point_boundary(self):
        self.client.force_login(self.admin)
        first_points = '[{"lat":16.8,"lng":81.5},{"lat":16.9,"lng":81.5},{"lat":16.9,"lng":81.6},{"lat":16.8,"lng":81.6}]'
        second_points = '[{"lat":17.0,"lng":82.0},{"lat":17.1,"lng":82.0},{"lat":17.1,"lng":82.1},{"lat":17.0,"lng":82.1}]'

        first = self.client.post(reverse("operations:save_boundary"), {"points": first_points})
        second = self.client.post(reverse("operations:save_boundary"), {"points": second_points})

        self.assertRedirects(first, reverse("operations:admin_dashboard"))
        self.assertRedirects(second, reverse("operations:admin_dashboard"))
        self.assertEqual(ServiceBoundary.objects.count(), 1)
        boundary = ServiceBoundary.objects.get()
        self.assertEqual(len(boundary.points), 4)
        self.assertEqual(boundary.points[0], {"lat": 17.0, "lng": 82.0})

    def test_map_rotation_controls_and_endpoint_are_removed(self):
        self.client.force_login(self.admin)
        dashboard = self.client.get(reverse("operations:admin_dashboard"))
        self.assertNotContains(dashboard, "rotate-map-left")
        self.assertNotContains(dashboard, "rotate-map-right")
        self.assertNotContains(dashboard, "save-map-rotation")
        boundary_data = self.client.get(reverse("operations:boundary_api")).json()
        self.assertEqual(boundary_data, {"points": None})

    def test_boundary_requires_four_points(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse("operations:save_boundary"), {
            "points": '[{"lat":16.8,"lng":81.5},{"lat":16.9,"lng":81.5},{"lat":16.9,"lng":81.6}]',
        })

        self.assertRedirects(response, reverse("operations:admin_dashboard"))
        self.assertFalse(ServiceBoundary.objects.exists())

    def test_admin_map_has_marker_form_and_no_boundary_drawing_control(self):
        ServiceBoundary.objects.create(
            points=[
                {"lat": 16.8, "lng": 81.5},
                {"lat": 16.9, "lng": 81.5},
                {"lat": 16.9, "lng": 81.6},
                {"lat": 16.8, "lng": 81.6},
            ],
            created_by=self.admin,
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse("operations:admin_dashboard"))

        self.assertContains(response, 'id="marker-form"')
        self.assertContains(response, "Add a permanent public dustbin marker")
        self.assertNotContains(response, 'id="id_name"')
        self.assertNotContains(response, 'id="id_category"')
        self.assertContains(response, 'id="id_latitude"')
        self.assertContains(response, 'id="id_longitude"')
        self.assertContains(response, "Choose coordinates on map")
        self.assertContains(response, "Redraw service boundary")
        self.assertContains(response, "Click four points around the boundary in order.")
        self.assertContains(response, 'id="boundary-selection-status"')
        self.assertContains(response, "Open complaint management")
        self.assertContains(response, "Open worker operations")
        self.assertNotContains(response, "Recycling centers")
        self.assertNotContains(response, "Collection points")

    def test_citizen_cannot_save_service_boundary(self):
        self.client.force_login(self.citizen)
        response = self.client.post(reverse("operations:save_boundary"), {
            "points": '[{"lat":16.8,"lng":81.5},{"lat":16.9,"lng":81.5},{"lat":16.9,"lng":81.6}]',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:dashboard"))
        self.assertFalse(ServiceBoundary.objects.exists())

    def test_citizen_cannot_add_map_markers(self):
        self.client.force_login(self.citizen)
        response = self.client.post(reverse("operations:create_dustbin"), {
            "description": "",
            "latitude": "16.8",
            "longitude": "81.5",
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("accounts:dashboard"))
        self.assertFalse(Dustbin.objects.exists())

    def test_administrator_can_only_add_map_marker_inside_service_boundary(self):
        ServiceBoundary.objects.create(
            points=[
                {"lat": 16.8, "lng": 81.5},
                {"lat": 16.9, "lng": 81.5},
                {"lat": 16.9, "lng": 81.6},
                {"lat": 16.8, "lng": 81.6},
            ],
            created_by=self.admin,
        )
        self.client.force_login(self.admin)
        marker_data = {
            "name": "Community bin",
            "category": "recycling_center",
            "description": "",
            "latitude": "16.85",
            "longitude": "81.55",
        }

        inside_response = self.client.post(reverse("operations:create_dustbin"), marker_data)
        marker_data["latitude"] = "17.0"
        outside_response = self.client.post(reverse("operations:create_dustbin"), marker_data)

        self.assertRedirects(inside_response, reverse("operations:admin_dashboard"))
        self.assertRedirects(outside_response, reverse("operations:admin_dashboard"))
        self.assertEqual(Dustbin.objects.count(), 1)
        marker = Dustbin.objects.get()
        self.assertEqual(marker.name, f"DBno{marker.pk}")
        self.assertEqual(marker.category, Dustbin.Category.PUBLIC_DUSTBIN)
