from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from citizen_services.models import Complaint, PickupRequest

from .models import (
    CitizenConfirmation,
    Crew,
    CrewAssignment,
    CrewMember,
    Notification,
    TaskStatusHistory,
    Vehicle,
    WorkerLocation,
)
from .services import CrewAssignmentError, assign_task_crew, change_crew_leader, process_confirmation_deadlines


class SharedTaskCrewWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="task-admin",
            email="task-admin@example.test",
            password="SecurePass123!",
            role=User.Role.ADMINISTRATOR,
        )
        self.citizen = User.objects.create_user(
            username="task-citizen",
            email="task-citizen@example.test",
            password="SecurePass123!",
        )
        self.driver = self._worker("driver", User.Role.DRIVER)
        self.leader = self._worker("leader", User.Role.CLEANER)
        self.worker = self._worker("worker", User.Role.CLEANER)
        self.vehicle = Vehicle.objects.create(
            identifier="TASK-VAN",
            registration_number="TASK-101",
            vehicle_type="Van",
        )

    def _worker(self, username, role):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.test",
            password="SecurePass123!",
            role=role,
            approved=True,
        )
        WorkerLocation.objects.create(
            user=user,
            latitude="16.833944",
            longitude="81.531444",
            is_signed_in=True,
            availability=WorkerLocation.Availability.AVAILABLE,
        )
        return user

    def _complaint(self):
        return Complaint.objects.create(
            citizen=self.citizen,
            category=Complaint.Category.OVERFLOWING_BIN,
            description="Waste needs collection.",
            photo="",
            latitude="16.833944",
            longitude="81.531444",
        )

    def test_admin_pages_require_an_admin_session(self):
        admin_dashboard = reverse("operations:admin_dashboard")
        complaint_management = reverse("operations:complaint_management")

        for path in (admin_dashboard, complaint_management):
            response = self.client.get(path)
            self.assertRedirects(response, f"{reverse('accounts:login')}?next={path}")

        self.client.force_login(self.citizen)
        for path in (admin_dashboard, complaint_management):
            response = self.client.get(path)
            self.assertRedirects(response, reverse("accounts:dashboard"), fetch_redirect_response=False)

    def test_complaint_actions_are_collapsed_until_requested(self):
        complaint = self._complaint()
        self.client.force_login(self.admin)

        response = self.client.get(reverse("operations:complaint_management"))

        self.assertContains(response, '<details class="task-actions"')
        self.assertContains(response, "<summary>Take action</summary>")
        self.assertContains(response, "Allocate an existing crew")
        self.assertContains(response, "Create crew in Worker operations")
        self.assertContains(response, "Cancel complaint")
        self.assertNotContains(response, '<details class="task-actions" open')

    def test_worker_operations_uses_multi_select_checkboxes_in_creation_order(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("operations:worker_management"))

        self.assertContains(response, 'type="checkbox"')
        self.assertContains(response, "Search drivers")
        self.assertContains(response, "Search workers")
        self.assertContains(response, "Search vehicles")
        body = response.content.decode()
        self.assertLess(body.index('name="drivers"'), body.index('name="workers"'))
        self.assertLess(body.index('name="workers"'), body.index('name="vehicles"'))
        self.assertLess(body.index('name="vehicles"'), body.index("Crew Leader (choose from selected drivers/workers)"))
        self.assertContains(
            response,
            '<select name="crew_leader" id="id_crew_leader" class="crew-leader-select" required>'
            '<option value="">Select a crew member above</option></select>',
        )

    def test_selectable_member_labels_include_details_used_for_crew_leader(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("operations:worker_management"))

        self.assertContains(response, "driver@example.test · Driver")
        self.assertContains(response, "leader@example.test · Cleaner")

    def _assign_new_crew(self, task):
        self.client.force_login(self.admin)
        task_type = "COMPLAINT"
        task_page = self.client.get(reverse("operations:complaint_management"))
        self.assertContains(task_page, "Create crew in Worker operations")
        worker_page = self.client.get(
            f"{reverse('operations:worker_management')}?complaint_id={task.pk}#crews"
        )
        self.assertContains(worker_page, f'name="complaint_id" value="{task.pk}"')
        create_response = self.client.post(
            reverse("operations:create_crew"),
            {
                "complaint_id": str(task.pk),
                "name": f"Crew for {task.pk}",
                "drivers": [str(self.driver.pk)],
                "workers": [str(self.leader.pk), str(self.worker.pk)],
                "vehicles": [str(self.vehicle.pk)],
                "crew_leader": str(self.leader.pk),
            },
        )
        crew = Crew.objects.get(name=f"Crew for {task.pk}")
        self.assertRedirects(
            create_response,
            f"{reverse('operations:complaint_management')}?next_complaint={task.pk}"
            f"&created_crew={crew.pk}#complaint-{task.pk}",
            fetch_redirect_response=False,
        )
        next_step = self.client.get(create_response["Location"])
        self.assertContains(next_step, '<details class="task-actions" open>')
        self.assertContains(next_step, "Next step: assign the crew you created")
        self.assertContains(next_step, 'name="crew_id"')
        response = self.client.post(
            reverse("operations:assign_task", args=[task_type, task.pk]),
            {"crew_id": str(crew.pk)},
        )
        self.assertRedirects(response, reverse("operations:complaint_management"))
        task.refresh_from_db()
        self.assertEqual(task.status, Complaint.Status.ASSIGNED)
        crew = task.assigned_crew
        self.assertEqual(crew.crew_leader, self.leader)
        self.assertEqual(crew.vehicle, self.vehicle)
        self.assertEqual(CrewMember.objects.filter(crew=crew, is_active=True).count(), 3)
        return crew, CrewAssignment.objects.get(complaint=task)

    def test_complaint_form_creates_flexible_crew_and_assigns_resources(self):
        complaint = self._complaint()
        crew, assignment = self._assign_new_crew(complaint)

        self.assertEqual(assignment.status, CrewAssignment.Status.ACTIVE)
        self.assertEqual(
            set(WorkerLocation.objects.filter(user__in=[self.driver, self.leader, self.worker]).values_list("availability", flat=True)),
            {WorkerLocation.Availability.ASSIGNED},
        )
        self.assertEqual(
            TaskStatusHistory.objects.filter(complaint=complaint).values_list("status", flat=True).last(),
            Complaint.Status.ASSIGNED,
        )
        self.assertEqual(Notification.objects.filter(recipient__in=[self.driver, self.leader, self.worker]).count(), 3)

    def test_leader_can_change_only_to_a_member_and_location_access_is_scoped(self):
        complaint = self._complaint()
        crew, _assignment = self._assign_new_crew(complaint)

        updated = change_crew_leader(
            crew_id=crew.pk,
            leader_id=self.worker.pk,
            administrator=self.admin,
        )
        self.assertEqual(updated.crew_leader, self.worker)
        history = list(crew.leader_history.order_by("designated_at"))
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].user, self.leader)
        self.assertIsNotNone(history[0].ended_at)
        self.assertEqual(history[1].user, self.worker)
        self.assertIsNone(history[1].ended_at)

        with self.assertRaises(CrewAssignmentError):
            change_crew_leader(
                crew_id=crew.pk,
                leader_id=self.citizen.pk,
                administrator=self.admin,
            )

        self.client.force_login(self.worker)
        locations = self.client.get(reverse("operations:crew_member_locations_api", args=[crew.pk]))
        self.assertEqual(locations.status_code, 200)
        self.assertEqual(len(locations.json()["members"]), 3)
        self.client.force_login(self.leader)
        denied = self.client.get(reverse("operations:crew_member_locations_api", args=[crew.pk]))
        self.assertEqual(denied.status_code, 403)

        self.client.force_login(self.admin)
        map_data = self.client.get(reverse("operations:active_crews_map_api")).json()["crews"][0]
        self.assertEqual(map_data["leader"], self.worker.username)
        self.assertNotIn("members", map_data)

    def test_signing_in_again_keeps_assigned_worker_unavailable(self):
        complaint = self._complaint()
        self._assign_new_crew(complaint)
        location = WorkerLocation.objects.get(user=self.leader)
        location.is_signed_in = False
        location.save(update_fields=["is_signed_in"])
        self.assertEqual(location.availability, WorkerLocation.Availability.ASSIGNED)
        self.assertFalse(location.is_signed_in)

        self.client.logout()
        response = self.client.post(reverse("accounts:login"), {
            "username": self.leader.email,
            "password": "SecurePass123!",
        })

        self.assertRedirects(response, reverse("operations:worker_dashboard"))
        location.refresh_from_db()
        self.assertEqual(location.availability, WorkerLocation.Availability.ASSIGNED)
        self.assertTrue(location.is_signed_in)

    def test_pickup_uses_the_same_admin_crew_workflow_and_preserves_task_type(self):
        pickup = PickupRequest.objects.create(
            citizen=self.citizen,
            address="12 Green Street",
            category=PickupRequest.Category.HOUSEHOLD,
            quantity=2,
            scheduled_at=timezone.now() + timedelta(days=1),
            latitude="16.833944",
            longitude="81.531444",
        )
        self.client.force_login(self.admin)
        pending_page = self.client.get(reverse("operations:pickup_management"))
        self.assertContains(pending_page, "Allocate an existing crew")
        self.assertContains(pending_page, "Create crew in Worker operations")
        self.assertContains(pending_page, "Cancel pickup")
        self.assertContains(pending_page, "Status history")
        worker_page = self.client.get(
            f"{reverse('operations:worker_management')}?pickup_id={pickup.pk}#crews"
        )
        self.assertContains(worker_page, f'name="pickup_id" value="{pickup.pk}"')
        create_response = self.client.post(
            reverse("operations:create_crew"),
            {
                "pickup_id": str(pickup.pk),
                "name": "Pickup crew",
                "drivers": [str(self.driver.pk)],
                "workers": [str(self.leader.pk)],
                "vehicles": [str(self.vehicle.pk)],
                "crew_leader": str(self.leader.pk),
            },
        )
        crew = Crew.objects.get(name="Pickup crew")
        self.assertRedirects(
            create_response,
            f"{reverse('operations:pickup_management')}?next_pickup={pickup.pk}"
            f"&created_crew={crew.pk}#pickup-{pickup.pk}",
            fetch_redirect_response=False,
        )
        next_step = self.client.get(create_response["Location"])
        self.assertContains(next_step, '<details class="task-actions" open>')
        self.assertContains(next_step, "Next step: assign the crew you created")
        assignment_response = self.client.post(
            reverse("operations:assign_task", args=["HOME_PICKUP", pickup.pk]),
            {"crew_id": str(crew.pk)},
        )
        self.assertRedirects(assignment_response, reverse("operations:pickup_management"))

        pickup.refresh_from_db()
        self.assertEqual(pickup.status, PickupRequest.Status.ASSIGNED)
        self.assertEqual(pickup.assigned_crew, crew)
        assignment = CrewAssignment.objects.get(pickup=pickup)
        self.assertEqual(assignment.task_type, "HOME_PICKUP")

    def test_only_the_designated_leader_can_progress_and_citizen_can_dispute_or_confirm(self):
        complaint = self._complaint()
        crew, assignment = self._assign_new_crew(complaint)

        self.client.force_login(self.worker)
        forbidden = self.client.post(
            reverse("operations:update_task_progress", args=[assignment.pk]),
            {"status": Complaint.Status.CREW_ON_THE_WAY},
        )
        self.assertEqual(forbidden.status_code, 400)
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, Complaint.Status.ASSIGNED)

        self.client.force_login(self.leader)
        worker_page = self.client.get(reverse("operations:worker_dashboard"))
        self.assertContains(worker_page, "Navigate to Assigned Location")
        self.assertContains(worker_page, reverse("operations:crew_member_locations_api", args=[crew.pk]))
        for status in [
            Complaint.Status.CREW_ON_THE_WAY,
            Complaint.Status.ARRIVED,
            Complaint.Status.IN_PROGRESS,
            Complaint.Status.COMPLETED_AWAITING_CONFIRMATION,
        ]:
            response = self.client.post(
                reverse("operations:update_task_progress", args=[assignment.pk]),
                {"status": status, "remarks": "Work progress recorded."},
            )
            self.assertEqual(response.status_code, 200)

        complaint.refresh_from_db()
        confirmation = CitizenConfirmation.objects.get(complaint=complaint)
        self.assertEqual(complaint.status, Complaint.Status.COMPLETED_AWAITING_CONFIRMATION)
        self.assertGreater(confirmation.deadline, timezone.now())

        self.client.force_login(self.citizen)
        citizen_page = self.client.get(reverse("citizen:complaints"))
        self.assertContains(citizen_page, "Confirm completion")
        dispute = self.client.post(
            reverse("citizen:completion_response", args=["COMPLAINT", complaint.pk]),
            {"response_type": "dispute", "response": "The collection is incomplete."},
        )
        self.assertRedirects(dispute, reverse("citizen:complaints"))
        complaint.refresh_from_db()
        assignment.refresh_from_db()
        self.assertEqual(complaint.status, Complaint.Status.ADMIN_REVIEW)
        self.assertEqual(assignment.status, CrewAssignment.Status.DISPUTED)
        self.assertTrue(crew.member_assignments.filter(is_active=True).exists())

        self.client.force_login(self.admin)
        resolved = self.client.post(
            reverse("operations:resolve_dispute", args=["COMPLAINT", complaint.pk]),
            {"resolution_action": "return_to_work", "resolution": "Crew will finish the remaining work."},
        )
        self.assertRedirects(resolved, reverse("operations:complaint_management"))
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, CrewAssignment.Status.ACTIVE)

        self.client.force_login(self.leader)
        complete_again = self.client.post(
            reverse("operations:update_task_progress", args=[assignment.pk]),
            {"status": Complaint.Status.COMPLETED_AWAITING_CONFIRMATION, "remarks": "Work complete."},
        )
        self.assertEqual(complete_again.status_code, 200)
        self.client.force_login(self.citizen)
        confirmed = self.client.post(
            reverse("citizen:completion_response", args=["COMPLAINT", complaint.pk]),
            {"response_type": "confirm"},
        )
        self.assertRedirects(confirmed, reverse("citizen:complaints"))
        complaint.refresh_from_db()
        assignment.refresh_from_db()
        crew.refresh_from_db()
        self.assertEqual(complaint.status, Complaint.Status.CLOSED)
        self.assertEqual(assignment.status, CrewAssignment.Status.COMPLETED)
        self.assertFalse(crew.is_active)
        self.assertFalse(crew.member_assignments.filter(is_active=True).exists())
        self.assertEqual(
            WorkerLocation.objects.get(user=self.worker).availability,
            WorkerLocation.Availability.AVAILABLE,
        )

    def test_confirmation_timeout_sends_reminder_then_requires_admin_resolution(self):
        complaint = self._complaint()
        crew, assignment = self._assign_new_crew(complaint)
        self.client.force_login(self.leader)
        for status in [
            Complaint.Status.CREW_ON_THE_WAY,
            Complaint.Status.ARRIVED,
            Complaint.Status.IN_PROGRESS,
            Complaint.Status.COMPLETED_AWAITING_CONFIRMATION,
        ]:
            self.client.post(
                reverse("operations:update_task_progress", args=[assignment.pk]),
                {"status": status},
            )
        confirmation = CitizenConfirmation.objects.get(complaint=complaint)
        confirmation.deadline = timezone.now() + timedelta(minutes=45)
        confirmation.save(update_fields=["deadline"])
        reminder_result = process_confirmation_deadlines()
        self.assertEqual(reminder_result["reminders_sent"], 1)
        self.assertTrue(Notification.objects.filter(recipient=self.citizen, message__icontains="Reminder").exists())

        confirmation.deadline = timezone.now() - timedelta(seconds=1)
        confirmation.save(update_fields=["deadline"])
        timeout_result = process_confirmation_deadlines()
        self.assertEqual(timeout_result["reviews_created"], 1)
        complaint.refresh_from_db()
        assignment.refresh_from_db()
        crew.refresh_from_db()
        self.assertEqual(complaint.status, Complaint.Status.ADMIN_REVIEW)
        self.assertEqual(assignment.status, CrewAssignment.Status.DISPUTED)
        self.assertTrue(crew.is_active)
