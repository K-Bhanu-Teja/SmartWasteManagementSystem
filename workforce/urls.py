from django.urls import path
from . import views

app_name = "operations"
urlpatterns = [
    # Administrator Dashboard & Modules
    path("admin/", views.admin_dashboard, name="admin_dashboard"),
    path("admin/requests/", views.request_management, name="request_management"),
    path("admin/requests/<int:request_id>/", views.request_detail_admin, name="request_detail_admin"),
    path("admin/dustbins/", views.dustbin_management, name="dustbin_management"),
    path("admin/dustbins/<int:dustbin_id>/", views.dustbin_update, name="dustbin_update"),
    path("admin/dustbins/<int:dustbin_id>/delete/", views.dustbin_delete, name="dustbin_delete"),
    path("admin/workers/", views.worker_management, name="worker_management"),
    path("admin/workers/<int:worker_id>/edit/", views.worker_update, name="worker_update"),
    path("admin/crews/", views.crew_management, name="crew_management"),
    path("admin/crews/<int:crew_id>/", views.crew_detail, name="crew_detail"),
    path("admin/crews/<int:crew_id>/dissolve/", views.dissolve_crew_view, name="dissolve_crew"),
    path("admin/vehicles/", views.vehicle_management, name="vehicle_management"),
    path("admin/vehicles/assign-driver/", views.assign_vehicle_driver, name="assign_vehicle_driver"),
    path("admin/vehicles/assignments/<int:assignment_id>/release/", views.release_vehicle_assignment, name="release_vehicle_assignment"),
    path("admin/tasks/", views.task_management, name="task_management"),
    path("admin/tasks/<int:task_id>/", views.task_detail, name="task_detail"),

    # Worker Dashboard & Actions
    path("worker/", views.worker_dashboard, name="worker_dashboard"),
    path("worker/availability/", views.worker_set_availability, name="worker_set_availability"),
    path("worker/tasks/<int:task_id>/start/", views.worker_start_task, name="worker_start_task"),
    path("worker/tasks/<int:task_id>/complete/", views.worker_complete_task, name="worker_complete_task"),
]
