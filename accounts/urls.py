from django.urls import path
from . import views

app_name = "accounts"
urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("forgot-password/", views.password_reset_request, name="password_reset"),
    path("forgot-password/verify/", views.password_reset_verify, name="password_reset_verify"),
]
