from functools import wraps
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.forms import WorkerRegistrationForm, WorkerUpdateForm
from accounts.models import WorkerProfile
from citizen_services.forms import DustbinForm
from citizen_services.models import CleaningHistory, Dustbin, Request
from .forms import TaskCompletionForm, TaskCreationForm, VehicleAssignmentForm, VehicleForm
from .models import Crew, CrewMember, Notification, Task, Vehicle, VehicleAssignment
from .services import (
    assign_task_to_worker_or_crew,
    complete_task_execution,
    create_temporary_crew,
    dissolve_temporary_crew,
    notify_admins,
    notify_user,
    start_task_execution,
    verify_task_completion,
)

User = get_user_model()


def administrator_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.role != User.Role.ADMINISTRATOR and not request.user.is_superuser:
            messages.error(request, "Administrator privileges required.")
            return redirect("accounts:dashboard")
        return view(request, *args, **kwargs)
    return wrapped


def worker_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.role != User.Role.WORKER:
            return redirect("citizen:dashboard")
        return view(request, *args, **kwargs)
    return wrapped


# ==============================================================================
# ADMINISTRATOR VIEWS
# ==============================================================================

@administrator_required
def admin_dashboard(request):
    """Admin Dashboard Overview: Live database statistics and quick links."""
    total_dustbins = Dustbin.objects.filter(is_active=True).count()
    total_requests = Request.objects.count()
    pending_requests = Request.objects.filter(
        status__in=[Request.Status.SUBMITTED, Request.Status.UNDER_REVIEW]
    ).count()

    available_workers = WorkerProfile.objects.filter(
        availability=WorkerProfile.Availability.ACTIVE,
        user__is_active=True,
    ).count()

    assigned_workers = WorkerProfile.objects.filter(
        availability=WorkerProfile.Availability.ASSIGNED,
        user__is_active=True,
    ).count()

    active_crews = Crew.objects.filter(is_active=True).count()
    pending_tasks = Task.objects.filter(status=Task.Status.PENDING).count()
    completed_tasks = Task.objects.filter(status=Task.Status.COMPLETED).count()

    notifications = Notification.objects.filter(recipient=request.user).order_by("-created_at")[:8]
    recent_requests = Request.objects.order_by("-created_at")[:5]
    recent_tasks = Task.objects.order_by("-created_at")[:5]

    return render(
        request,
        "operations/admin_dashboard.html",
        {
            "total_dustbins": total_dustbins,
            "total_requests": total_requests,
            "pending_requests": pending_requests,
            "available_workers": available_workers,
            "assigned_workers": assigned_workers,
            "active_crews": active_crews,
            "pending_tasks": pending_tasks,
            "completed_tasks": completed_tasks,
            "notifications": notifications,
            "recent_requests": recent_requests,
            "recent_tasks": recent_tasks,
        },
    )


# ------------------------------------------------------------------------------
# 10.2 Request Management
# ------------------------------------------------------------------------------

@administrator_required
def request_management(request):
    """View and filter all citizen requests."""
    status_filter = request.GET.get("status", "")
    cause_filter = request.GET.get("cause", "")

    requests_qs = Request.objects.all().select_related("citizen")
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)
    if cause_filter:
        requests_qs = requests_qs.filter(cause=cause_filter)

    return render(
        request,
        "operations/request_management.html",
        {
            "requests": requests_qs.order_by("-created_at"),
            "status_filter": status_filter,
            "cause_filter": cause_filter,
            "statuses": Request.Status.choices,
            "causes": Request.Cause.choices,
        },
    )


@administrator_required
def request_detail_admin(request, request_id):
    """View full request details, photograph, map, and approve/reject/generate task actions."""
    req_item = get_object_or_404(Request, pk=request_id)
    task = getattr(req_item, "task", None)

    if request.method == "POST":
        action = request.POST.get("action")
        admin_remarks = request.POST.get("admin_remarks", "").strip()

        if action == "approve":
            req_item.status = Request.Status.APPROVED
            req_item.admin_remarks = admin_remarks or "Approved by Administrator."
            req_item.save(update_fields=["status", "admin_remarks", "updated_at"])
            notify_user(
                req_item.citizen,
                f"Your request '{req_item.title}' has been APPROVED by the administrator.",
                link=f"/citizen/requests/{req_item.pk}/",
            )
            messages.success(request, f"Request #{req_item.pk} approved.")
            return redirect("operations:request_detail_admin", request_id=req_item.pk)

        elif action == "reject":
            req_item.status = Request.Status.REJECTED
            req_item.admin_remarks = admin_remarks or "Rejected by Administrator."
            req_item.save(update_fields=["status", "admin_remarks", "updated_at"])
            notify_user(
                req_item.citizen,
                f"Your request '{req_item.title}' was rejected. Reason: {req_item.admin_remarks}",
                link=f"/citizen/requests/{req_item.pk}/",
            )
            messages.info(request, f"Request #{req_item.pk} rejected.")
            return redirect("operations:request_detail_admin", request_id=req_item.pk)

        elif action == "generate_task":
            # Only approved requests can generate tasks, prevent duplicate
            if req_item.status != Request.Status.APPROVED:
                messages.error(request, "Only APPROVED requests can generate tasks.")
            elif task is not None:
                messages.warning(request, "A task has already been generated for this request.")
            else:
                cat = Task.Category.COMPLAINT_RESOLUTION
                if req_item.cause == Request.Cause.SCHEDULED_WASTE_PICKUP:
                    cat = Task.Category.HOUSEHOLD_COLLECTION
                elif req_item.cause == Request.Cause.OVERFLOWING_DUSTBIN:
                    cat = Task.Category.DUSTBIN_CLEANING

                new_task = Task.objects.create(
                    title=f"Task: {req_item.title}",
                    category=cat,
                    description=req_item.description,
                    request=req_item,
                    created_by=request.user,
                    latitude=req_item.latitude,
                    longitude=req_item.longitude,
                    location_name=req_item.address or "",
                    status=Task.Status.PENDING,
                )
                messages.success(request, f"Task #{new_task.pk} successfully generated from request #{req_item.pk}.")
                return redirect("operations:task_detail", task_id=new_task.pk)

    return render(
        request,
        "operations/request_detail_admin.html",
        {
            "request_item": req_item,
            "task": task,
        },
    )


# ------------------------------------------------------------------------------
# 10.3 Dustbin Management
# ------------------------------------------------------------------------------

@administrator_required
def dustbin_management(request):
    """View all dustbins on map and in list, with add dustbin modal/form."""
    form = DustbinForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dustbin = form.save()
        messages.success(request, f"Dustbin {dustbin.name} registered successfully.")
        return redirect("operations:dustbin_management")

    dustbins = Dustbin.objects.all().order_by("name")
    return render(
        request,
        "operations/dustbin_management.html",
        {
            "dustbins": dustbins,
            "form": form,
        },
    )


@administrator_required
def dustbin_update(request, dustbin_id):
    """Update dustbin details or cleaning status."""
    dustbin = get_object_or_404(Dustbin, pk=dustbin_id)
    form = DustbinForm(request.POST or None, instance=dustbin)
    if request.method == "POST" and form.is_valid():
        dustbin = form.save()
        messages.success(request, f"Dustbin {dustbin.name} updated.")
        return redirect("operations:dustbin_management")

    cleaning_history = dustbin.cleaning_history.all()
    return render(
        request,
        "operations/dustbin_form.html",
        {
            "form": form,
            "dustbin": dustbin,
            "cleaning_history": cleaning_history,
        },
    )


@administrator_required
@require_POST
def dustbin_delete(request, dustbin_id):
    """Delete a dustbin."""
    dustbin = get_object_or_404(Dustbin, pk=dustbin_id)
    name = dustbin.name
    dustbin.delete()
    messages.success(request, f"Dustbin {name} has been deleted.")
    return redirect("operations:dustbin_management")


# ------------------------------------------------------------------------------
# 10.4 Worker Management
# ------------------------------------------------------------------------------

@administrator_required
def worker_management(request):
    """View registered workers, filter by designation/availability, and register worker."""
    form = WorkerRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        worker_user = form.save()
        messages.success(request, f"Worker {worker_user.get_full_name() or worker_user.username} registered successfully.")
        return redirect("operations:worker_management")

    designation_filter = request.GET.get("designation", "")
    availability_filter = request.GET.get("availability", "")

    workers_qs = WorkerProfile.objects.select_related("user").order_by("user__first_name")
    if designation_filter:
        workers_qs = workers_qs.filter(designation=designation_filter)
    if availability_filter:
        workers_qs = workers_qs.filter(availability=availability_filter)

    # Annotate active crew if any
    workers_list = []
    for wp in workers_qs:
        active_crew_membership = CrewMember.objects.filter(user=wp.user, crew__is_active=True, is_active=True).first()
        workers_list.append({
            "profile": wp,
            "active_crew": active_crew_membership.crew if active_crew_membership else None,
        })

    return render(
        request,
        "operations/worker_management.html",
        {
            "workers": workers_list,
            "form": form,
            "designation_filter": designation_filter,
            "availability_filter": availability_filter,
            "designations": WorkerProfile.Designation.choices,
            "availabilities": WorkerProfile.Availability.choices,
        },
    )


@administrator_required
def worker_update(request, worker_id):
    """Update worker information."""
    profile = get_object_or_404(WorkerProfile, pk=worker_id)
    form = WorkerUpdateForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Worker profile updated for {profile.user.username}.")
        return redirect("operations:worker_management")

    return render(
        request,
        "operations/worker_form.html",
        {
            "form": form,
            "worker_profile": profile,
        },
    )


# ------------------------------------------------------------------------------
# 10.5 Dynamic Crew Management
# ------------------------------------------------------------------------------

@administrator_required
def crew_management(request):
    """Dynamic Crew Management: view available workers, create crew, view & dissolve crews."""
    active_crews = Crew.objects.filter(is_active=True).prefetch_related("members__user__worker_profile")
    dissolved_crews = Crew.objects.filter(is_active=False).prefetch_related("members__user__worker_profile").order_by("-dissolved_at")

    # Available workers for new crew: must be ACTIVE and not in an active crew
    assigned_worker_ids = CrewMember.objects.filter(crew__is_active=True, is_active=True).values_list("user_id", flat=True)
    available_workers = User.objects.filter(
        role=User.Role.WORKER,
        worker_profile__availability=WorkerProfile.Availability.ACTIVE,
        is_active=True,
    ).exclude(pk__in=assigned_worker_ids).select_related("worker_profile")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_crew":
            crew_name = request.POST.get("crew_name", "").strip()
            leader_id = request.POST.get("crew_leader")
            member_ids = request.POST.getlist("members")

            if not crew_name:
                messages.error(request, "Crew name is required.")
            elif not leader_id:
                messages.error(request, "You must designate exactly one Crew Leader.")
            elif not member_ids:
                messages.error(request, "Select at least one worker for the crew.")
            else:
                try:
                    leader_user = User.objects.get(pk=leader_id, role=User.Role.WORKER)
                    member_users = User.objects.filter(pk__in=member_ids, role=User.Role.WORKER)
                    crew = create_temporary_crew(
                        name=crew_name,
                        leader=leader_user,
                        members=member_users,
                        created_by=request.user,
                    )
                    messages.success(request, f"Temporary Crew '{crew.name}' created with leader {leader_user.get_full_name() or leader_user.username}.")
                    return redirect("operations:crew_management")
                except Exception as e:
                    messages.error(request, f"Failed to create crew: {e}")

    return render(
        request,
        "operations/crew_management.html",
        {
            "active_crews": active_crews,
            "dissolved_crews": dissolved_crews,
            "available_workers": available_workers,
        },
    )


@administrator_required
def crew_detail(request, crew_id):
    """View crew details, members, and assigned tasks."""
    crew = get_object_or_404(Crew, pk=crew_id)
    members = crew.members.all().select_related("user", "user__worker_profile")
    crew_tasks = crew.tasks.all().order_by("-created_at")

    return render(
        request,
        "operations/crew_detail.html",
        {
            "crew": crew,
            "members": members,
            "tasks": crew_tasks,
        },
    )


@administrator_required
@require_POST
def dissolve_crew_view(request, crew_id):
    """Dissolve an active temporary crew."""
    crew = get_object_or_404(Crew, pk=crew_id, is_active=True)
    dissolve_temporary_crew(crew)
    messages.success(request, f"Crew '{crew.name}' has been dissolved and its workers are now active.")
    return redirect("operations:crew_management")


# ------------------------------------------------------------------------------
# 10.6 Vehicle Management
# ------------------------------------------------------------------------------

@administrator_required
def vehicle_management(request):
    """Register vehicles, view availability, dynamically assign/change drivers."""
    vehicle_form = VehicleForm(request.POST or None)
    if request.method == "POST" and "submit_vehicle" in request.POST:
        if vehicle_form.is_valid():
            vehicle = vehicle_form.save()
            messages.success(request, f"Vehicle {vehicle.registration_number} registered.")
            return redirect("operations:vehicle_management")

    vehicles = Vehicle.objects.all().order_by("registration_number")

    # Current active assignments
    active_assignments = {va.vehicle_id: va for va in VehicleAssignment.objects.filter(is_active=True).select_related("driver")}

    # Available drivers: Workers with designation Driver not currently assigned to an active vehicle
    assigned_driver_ids = VehicleAssignment.objects.filter(is_active=True).values_list("driver_id", flat=True)
    available_drivers = User.objects.filter(
        role=User.Role.WORKER,
        worker_profile__designation=WorkerProfile.Designation.DRIVER,
        is_active=True,
    ).exclude(pk__in=assigned_driver_ids)

    vehicle_rows = []
    for v in vehicles:
        vehicle_rows.append({
            "vehicle": v,
            "current_assignment": active_assignments.get(v.pk),
        })

    return render(
        request,
        "operations/vehicle_management.html",
        {
            "vehicles": vehicle_rows,
            "available_drivers": available_drivers,
            "vehicle_form": vehicle_form,
        },
    )


@administrator_required
@require_POST
def assign_vehicle_driver(request):
    """Dynamically assign or reassign a driver to a vehicle."""
    vehicle_id = request.POST.get("vehicle_id")
    driver_id = request.POST.get("driver_id")

    vehicle = get_object_or_404(Vehicle, pk=vehicle_id)
    driver = get_object_or_404(User, pk=driver_id, role=User.Role.WORKER)

    with transaction.atomic():
        # Deactivate any previous active assignment for this vehicle or driver
        VehicleAssignment.objects.filter(vehicle=vehicle, is_active=True).update(is_active=False, released_at=timezone.now())
        VehicleAssignment.objects.filter(driver=driver, is_active=True).update(is_active=False, released_at=timezone.now())

        # Create new assignment
        assignment = VehicleAssignment.objects.create(
            vehicle=vehicle,
            driver=driver,
            is_active=True,
        )
        vehicle.is_available = False
        vehicle.save(update_fields=["is_available"])

        notify_user(
            driver,
            f"You have been assigned to vehicle {vehicle.registration_number} ({vehicle.vehicle_type}).",
            link="/operations/worker/",
        )

    messages.success(request, f"Assigned {driver.get_full_name() or driver.username} to {vehicle.registration_number}.")
    return redirect("operations:vehicle_management")


@administrator_required
@require_POST
def release_vehicle_assignment(request, assignment_id):
    """Release a driver from a vehicle."""
    assignment = get_object_or_404(VehicleAssignment, pk=assignment_id, is_active=True)
    with transaction.atomic():
        assignment.is_active = False
        assignment.released_at = timezone.now()
        assignment.save(update_fields=["is_active", "released_at"])

        assignment.vehicle.is_available = True
        assignment.vehicle.save(update_fields=["is_available"])

    messages.info(request, f"Vehicle {assignment.vehicle.registration_number} released.")
    return redirect("operations:vehicle_management")


# ------------------------------------------------------------------------------
# 10.7 Centralized Task Management
# ------------------------------------------------------------------------------

@administrator_required
def task_management(request):
    """Centralized task management: list, filter, and create tasks."""
    form = TaskCreationForm(request.POST or None)
    if request.method == "POST" and "create_task" in request.POST:
        if form.is_valid():
            task = form.save(commit=False)
            task.created_by = request.user
            # Check if assigned immediately
            if task.assigned_worker or task.assigned_crew:
                task.status = Task.Status.ASSIGNED
            task.save()
            if task.assigned_worker or task.assigned_crew:
                assign_task_to_worker_or_crew(task, task.assigned_worker, task.assigned_crew)
            messages.success(request, f"Task #{task.pk} '{task.title}' created.")
            return redirect("operations:task_management")

    status_filter = request.GET.get("status", "")
    category_filter = request.GET.get("category", "")

    tasks_qs = Task.objects.all().select_related("assigned_worker", "assigned_crew", "request")
    if status_filter:
        tasks_qs = tasks_qs.filter(status=status_filter)
    if category_filter:
        tasks_qs = tasks_qs.filter(category=category_filter)

    return render(
        request,
        "operations/task_management.html",
        {
            "tasks": tasks_qs.order_by("-created_at"),
            "form": form,
            "status_filter": status_filter,
            "category_filter": category_filter,
            "statuses": Task.Status.choices,
            "categories": Task.Category.choices,
        },
    )


@administrator_required
def task_detail(request, task_id):
    """View task details, location, assign worker/crew, monitor progress, verify completion."""
    task = get_object_or_404(Task, pk=task_id)

    available_workers = User.objects.filter(role=User.Role.WORKER, is_active=True).select_related("worker_profile")
    active_crews = Crew.objects.filter(is_active=True)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "assign":
            worker_id = request.POST.get("assigned_worker")
            crew_id = request.POST.get("assigned_crew")

            worker = User.objects.filter(pk=worker_id, role=User.Role.WORKER).first() if worker_id else None
            crew = Crew.objects.filter(pk=crew_id, is_active=True).first() if crew_id else None

            if not worker and not crew:
                messages.error(request, "Select either an individual worker or an active crew.")
            else:
                assign_task_to_worker_or_crew(task, worker=worker, crew=crew)
                messages.success(request, f"Task #{task.pk} assigned successfully.")
                return redirect("operations:task_detail", task_id=task.pk)

        elif action == "verify":
            admin_notes = request.POST.get("admin_notes", "").strip()
            verify_task_completion(task, request.user, admin_notes)
            messages.success(request, f"Task #{task.pk} completion verified! Linked request resolved.")
            return redirect("operations:task_detail", task_id=task.pk)

    return render(
        request,
        "operations/task_detail.html",
        {
            "task": task,
            "available_workers": available_workers,
            "active_crews": active_crews,
        },
    )


# ==============================================================================
# WORKER DASHBOARD VIEWS
# ==============================================================================

@worker_required
def worker_dashboard(request):
    """
    Worker Dashboard:
    - Worker Profile & Designation
    - Availability toggle (I'M AVAILABLE / I'M UNAVAILABLE)
    - My Tasks (Assigned, In Progress, Completed)
    - Active Crew Info & Leadership Controls
    """
    profile = get_object_or_404(WorkerProfile, user=request.user)

    # Check active crew membership
    active_membership = CrewMember.objects.filter(
        user=request.user,
        crew__is_active=True,
        is_active=True,
    ).select_related("crew__crew_leader").first()

    active_crew = active_membership.crew if active_membership else None
    is_crew_leader = active_membership.is_leader if active_membership else False

    # Worker tasks:
    # 1. Direct assignments
    # 2. Crew assignments
    crew_ids = [active_crew.pk] if active_crew else []
    tasks = Task.objects.filter(
        Q(assigned_worker=request.user) | Q(assigned_crew_id__in=crew_ids)
    ).order_by("-created_at")

    assigned_tasks = tasks.filter(status=Task.Status.ASSIGNED)
    in_progress_tasks = tasks.filter(status=Task.Status.IN_PROGRESS)
    completed_tasks = tasks.filter(status=Task.Status.COMPLETED)

    notifications = Notification.objects.filter(recipient=request.user).order_by("-created_at")[:6]

    return render(
        request,
        "operations/worker_dashboard.html",
        {
            "profile": profile,
            "active_crew": active_crew,
            "is_crew_leader": is_crew_leader,
            "assigned_tasks": assigned_tasks,
            "in_progress_tasks": in_progress_tasks,
            "completed_tasks": completed_tasks,
            "notifications": notifications,
        },
    )


@worker_required
@require_POST
def worker_set_availability(request):
    """
    Availability Management:
    - "I'M AVAILABLE" -> Sets status to ACTIVE, notifies admin.
    - "I'M UNAVAILABLE" -> Sets status to INACTIVE, notifies admin (blocked if in active crew).
    """
    status_choice = request.POST.get("availability")
    profile = get_object_or_404(WorkerProfile, user=request.user)

    # Check if worker is assigned to an active crew
    in_active_crew = CrewMember.objects.filter(
        user=request.user,
        crew__is_active=True,
        is_active=True,
    ).exists()

    if status_choice == "ACTIVE":
        profile.availability = WorkerProfile.Availability.ACTIVE
        profile.availability_updated_at = timezone.now()
        profile.save(update_fields=["availability", "availability_updated_at"])

        notify_admins(
            f"Worker {request.user.get_full_name() or request.user.username} is now AVAILABLE (ACTIVE).",
            link="/operations/admin/workers/",
        )
        messages.success(request, "Your status is now set to AVAILABLE.")

    elif status_choice == "INACTIVE":
        if in_active_crew:
            messages.error(request, "Workers assigned to an active crew cannot independently deactivate themselves.")
        else:
            profile.availability = WorkerProfile.Availability.INACTIVE
            profile.availability_updated_at = timezone.now()
            profile.save(update_fields=["availability", "availability_updated_at"])

            notify_admins(
                f"Worker {request.user.get_full_name() or request.user.username} is now UNAVAILABLE (INACTIVE).",
                link="/operations/admin/workers/",
            )
            messages.info(request, "Your status is now set to UNAVAILABLE.")

    return redirect("operations:worker_dashboard")


@worker_required
@require_POST
def worker_start_task(request, task_id):
    """Worker starts an ASSIGNED task -> transitions to IN_PROGRESS."""
    task = get_object_or_404(Task, pk=task_id)

    # Verify authorization: directly assigned worker or crew member/leader
    authorized = (task.assigned_worker == request.user)
    if not authorized and task.assigned_crew:
        authorized = CrewMember.objects.filter(crew=task.assigned_crew, user=request.user, is_active=True).exists()

    if not authorized:
        messages.error(request, "You are not authorized to start this task.")
        return redirect("operations:worker_dashboard")

    if task.status != Task.Status.ASSIGNED:
        messages.warning(request, "This task is not in ASSIGNED status.")
        return redirect("operations:worker_dashboard")

    start_task_execution(task, request.user)
    messages.success(request, f"Task #{task.pk} is now IN PROGRESS. Work safely!")
    return redirect("operations:worker_dashboard")


@worker_required
def worker_complete_task(request, task_id):
    """Worker submits completion photograph and remarks -> COMPLETED."""
    task = get_object_or_404(Task, pk=task_id)

    authorized = (task.assigned_worker == request.user)
    if not authorized and task.assigned_crew:
        authorized = CrewMember.objects.filter(crew=task.assigned_crew, user=request.user, is_active=True).exists()

    if not authorized:
        messages.error(request, "You are not authorized to complete this task.")
        return redirect("operations:worker_dashboard")

    if task.status != Task.Status.IN_PROGRESS:
        messages.warning(request, "This task must be IN PROGRESS before completion.")
        return redirect("operations:worker_dashboard")

    form = TaskCompletionForm(request.POST or None, request.FILES or None, instance=task)
    if request.method == "POST":
        if form.is_valid():
            complete_task_execution(
                task,
                photo=request.FILES.get("completion_photo"),
                remarks=form.cleaned_data["completion_remarks"],
                worker=request.user,
            )
            messages.success(request, f"Task #{task.pk} marked as COMPLETED and submitted for admin verification.")
            return redirect("operations:worker_dashboard")
        else:
            messages.error(request, "Both completion photograph and completion remarks are required.")

    return render(
        request,
        "operations/worker_task_complete.html",
        {
            "task": task,
            "form": form,
        },
    )
