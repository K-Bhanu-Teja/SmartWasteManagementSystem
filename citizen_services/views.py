from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import User
from workforce.models import Notification
from workforce.services import notify_admins
from .forms import UnifiedRequestForm
from .models import Dustbin, Request


def citizen_required(view):
    @login_required
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if request.user.role != User.Role.CITIZEN:
            return redirect("accounts:dashboard")
        return view(request, *args, **kwargs)
    return wrapped


def home(request):
    """Public home page showing dustbin locations and system introduction."""
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    dustbins = Dustbin.objects.filter(is_active=True)
    return render(request, "home.html", {"dustbins": dustbins})


@citizen_required
def nearby_dustbins(request):
    """Dedicated Citizen Nearby Dustbins view with geolocation and interactive map."""
    dustbins = Dustbin.objects.filter(is_active=True).order_by("name")
    return render(request, "citizen/nearby_dustbins.html", {"dustbins": dustbins})


@citizen_required
def dashboard(request):
    """Citizen dashboard: Dustbins map, quick stats, notifications, and navigation."""
    dustbins = Dustbin.objects.filter(is_active=True)
    my_requests = Request.objects.filter(citizen=request.user).order_by("-created_at")
    notifications = Notification.objects.filter(recipient=request.user).order_by("-created_at")[:10]

    return render(
        request,
        "citizen/dashboard.html",
        {
            "dustbins": dustbins,
            "total_requests": my_requests.count(),
            "pending_requests": my_requests.filter(status__in=[Request.Status.SUBMITTED, Request.Status.UNDER_REVIEW, Request.Status.APPROVED, Request.Status.ASSIGNED, Request.Status.IN_PROGRESS]).count(),
            "resolved_requests": my_requests.filter(status=Request.Status.RESOLVED).count(),
            "recent_requests": my_requests[:5],
            "notifications": notifications,
        },
    )


@citizen_required
def submit_request(request):
    """Unified request submission: complaints or scheduled household waste pickups."""
    form = UnifiedRequestForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        if form.is_valid():
            req_item = form.save(commit=False)
            req_item.citizen = request.user
            req_item.status = Request.Status.SUBMITTED
            req_item.save()

            # Notify Administrator of new citizen request
            notify_admins(
                f"New {req_item.cause} request submitted by {request.user.get_full_name() or request.user.username}: '{req_item.title}'",
                link="/operations/admin/requests/",
            )

            messages.success(request, f"Your request #{req_item.pk} '{req_item.title}' has been submitted successfully.")
            return redirect("citizen:my_requests")
        else:
            messages.error(request, "Please check the form for errors.")

    return render(request, "citizen/submit_request.html", {"form": form})


@citizen_required
def my_requests(request):
    """List citizen's own requests with filter and tracking."""
    status_filter = request.GET.get("status", "")
    requests_qs = Request.objects.filter(citizen=request.user)

    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)

    requests_list = requests_qs.order_by("-created_at")
    return render(
        request,
        "citizen/my_requests.html",
        {
            "requests": requests_list,
            "status_filter": status_filter,
            "statuses": Request.Status.choices,
        },
    )


@citizen_required
def request_detail(request, request_id):
    """View details, tracking status, and completion verification for a request."""
    req_item = get_object_or_404(Request, pk=request_id, citizen=request.user)
    # Check if a task exists and has completion info
    task = getattr(req_item, "task", None)
    return render(
        request,
        "citizen/request_detail.html",
        {
            "request_item": req_item,
            "task": task,
        },
    )


@citizen_required
@require_POST
def cancel_request(request, request_id):
    """Cancel a request before task is assigned/started."""
    req_item = get_object_or_404(Request, pk=request_id, citizen=request.user)
    # Can only cancel before task assignment
    if req_item.status in [Request.Status.SUBMITTED, Request.Status.UNDER_REVIEW, Request.Status.APPROVED]:
        req_item.status = Request.Status.CANCELLED
        req_item.save(update_fields=["status", "updated_at"])
        # If any pending task was generated, cancel it too
        if hasattr(req_item, "task") and req_item.task:
            task = req_item.task
            if task.status == "PENDING":
                task.status = "CANCELLED"
                task.save(update_fields=["status", "updated_at"])
        messages.success(request, f"Request #{req_item.pk} has been cancelled.")
    else:
        messages.error(request, "This request has already been assigned or processed and cannot be cancelled.")
    return redirect("citizen:my_requests")


@require_GET
def dustbins_api(request):
    """Returns active registered dustbins for Google Maps markers."""
    dustbins = Dustbin.objects.filter(is_active=True)
    data = [
        {
            "id": d.pk,
            "name": d.name,
            "description": d.description,
            "latitude": float(d.latitude),
            "longitude": float(d.longitude),
            "last_cleaned_at": d.last_cleaned_at.strftime("%b %d, %Y %I:%M %p") if d.last_cleaned_at else "Not recorded yet",
        }
        for d in dustbins
    ]
    return JsonResponse({"dustbins": data})
