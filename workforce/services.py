from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from accounts.models import WorkerProfile
from citizen_services.models import CleaningHistory, Request
from .models import Crew, CrewMember, Notification, Task, Vehicle, VehicleAssignment

User = get_user_model()


def notify_user(recipient, message, link=""):
    """Creates a notification for a user."""
    if recipient:
        return Notification.objects.create(recipient=recipient, message=message, link=link)


def notify_admins(message, link=""):
    """Notifies all active administrator accounts."""
    admins = User.objects.filter(role=User.Role.ADMINISTRATOR, is_active=True)
    notifications = [Notification(recipient=admin, message=message, link=link) for admin in admins]
    if notifications:
        Notification.objects.bulk_create(notifications)


def create_temporary_crew(name, leader, members, created_by=None):
    """
    Creates a dynamic temporary crew.
    - All selected workers must be ACTIVE and not in any active crew.
    - Exactly one leader must be designated.
    """
    with transaction.atomic():
        # Validate that leader is among the selected members
        member_ids = {m.pk for m in members}
        if leader.pk not in member_ids:
            members = list(members) + [leader]

        # Check that none of the members are in an active crew
        already_assigned = CrewMember.objects.filter(
            user__in=members,
            crew__is_active=True,
            is_active=True,
        ).select_related("user")
        if already_assigned.exists():
            names = ", ".join(m.user.get_full_name() or m.user.username for m in already_assigned)
            raise ValueError(f"The following worker(s) are already in an active crew: {names}")

        crew = Crew.objects.create(
            name=name,
            crew_leader=leader,
            created_by=created_by,
            is_active=True,
        )

        crew_members = []
        for worker in members:
            is_leader = (worker.pk == leader.pk)
            crew_members.append(
                CrewMember(
                    crew=crew,
                    user=worker,
                    is_leader=is_leader,
                    member_type="leader" if is_leader else "worker",
                    is_active=True,
                )
            )
        CrewMember.objects.bulk_create(crew_members)

        # Update workers' availability status to ASSIGNED
        WorkerProfile.objects.filter(user__in=members).update(
            availability=WorkerProfile.Availability.ASSIGNED,
            availability_updated_at=timezone.now(),
        )

        # Send notification to each crew member
        for worker in members:
            notify_user(
                worker,
                f"You have been assigned to Crew '{crew.name}'. Leader: {leader.get_full_name() or leader.username}.",
                link="/operations/worker/",
            )

        return crew


def dissolve_temporary_crew(crew):
    """
    Dissolves a temporary crew.
    - Preserves historical records.
    - Workers return to ACTIVE availability (unless inactive).
    """
    with transaction.atomic():
        crew.is_active = False
        crew.dissolved_at = timezone.now()
        crew.save(update_fields=["is_active", "dissolved_at"])

        # Mark member memberships as inactive
        memberships = CrewMember.objects.filter(crew=crew, is_active=True)
        user_ids = list(memberships.values_list("user_id", flat=True))
        memberships.update(is_active=False, released_at=timezone.now())

        # For these workers, return availability to ACTIVE
        WorkerProfile.objects.filter(user_id__in=user_ids).update(
            availability=WorkerProfile.Availability.ACTIVE,
            availability_updated_at=timezone.now(),
        )


def assign_task_to_worker_or_crew(task, worker=None, crew=None):
    """Assigns task to an individual worker or temporary crew."""
    with transaction.atomic():
        task.assigned_worker = worker
        task.assigned_crew = crew
        task.status = Task.Status.ASSIGNED
        task.save(update_fields=["assigned_worker", "assigned_crew", "status", "updated_at"])

        if task.request:
            task.request.status = Request.Status.ASSIGNED
            task.request.save(update_fields=["status", "updated_at"])

        # Notifications
        if worker:
            notify_user(worker, f"New task assigned: {task.title}", link="/operations/worker/")
        elif crew:
            members = [m.user for m in crew.members.filter(is_active=True).select_related("user")]
            for m in members:
                notify_user(m, f"New crew task assigned: {task.title}", link="/operations/worker/")


def start_task_execution(task, worker):
    """Worker starts an assigned task."""
    with transaction.atomic():
        task.status = Task.Status.IN_PROGRESS
        task.started_at = timezone.now()
        task.save(update_fields=["status", "started_at", "updated_at"])

        if task.request:
            task.request.status = Request.Status.IN_PROGRESS
            task.request.save(update_fields=["status", "updated_at"])


def complete_task_execution(task, photo, remarks, worker):
    """Worker submits completion with photo and remarks."""
    with transaction.atomic():
        task.status = Task.Status.COMPLETED
        task.completed_at = timezone.now()
        task.completion_photo = photo
        task.completion_remarks = remarks
        task.save(update_fields=["status", "completed_at", "completion_photo", "completion_remarks", "updated_at"])

        # Notify administrator
        notify_admins(
            f"Task #{task.pk} '{task.title}' has been completed by {worker.get_full_name() or worker.username}. Awaiting verification.",
            link="/operations/admin/tasks/",
        )


def verify_task_completion(task, admin_user, admin_notes=""):
    """Admin verifies task completion and resolves linked request."""
    with transaction.atomic():
        task.verified_by_admin = True
        task.verified_at = timezone.now()
        task.admin_notes = admin_notes
        task.save(update_fields=["verified_by_admin", "verified_at", "admin_notes", "updated_at"])

        # If linked to a citizen request, resolve it!
        if task.request:
            task.request.status = Request.Status.RESOLVED
            task.request.admin_remarks = f"Verified by Admin: {admin_notes}" if admin_notes else "Verified by Admin"
            task.request.save(update_fields=["status", "admin_remarks", "updated_at"])

            notify_user(
                task.request.citizen,
                f"Your request '{task.request.title}' has been successfully resolved!",
                link="/citizen/requests/",
            )

        # If linked to a dustbin, record cleaning history and update last_cleaned_at!
        if task.dustbin:
            task.dustbin.last_cleaned_at = task.completed_at or timezone.now()
            task.dustbin.save(update_fields=["last_cleaned_at", "updated_at"])

            CleaningHistory.objects.create(
                dustbin=task.dustbin,
                task=task,
                cleaned_by=task.assigned_worker or (task.assigned_crew.crew_leader if task.assigned_crew else admin_user),
                remarks=task.completion_remarks or "Verified cleaned.",
            )
