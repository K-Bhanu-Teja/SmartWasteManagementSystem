from django.urls import path
from . import views

app_name = "citizen"
urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("nearby-dustbins/", views.nearby_dustbins, name="nearby_dustbins"),
    path("submit/", views.submit_request, name="submit_request"),
    path("requests/", views.my_requests, name="my_requests"),
    path("requests/<int:request_id>/", views.request_detail, name="request_detail"),
    path("requests/<int:request_id>/cancel/", views.cancel_request, name="cancel_request"),
    path("api/dustbins/", views.dustbins_api, name="dustbins_api"),
]
