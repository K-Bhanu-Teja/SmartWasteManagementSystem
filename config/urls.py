from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

from citizen_services import views as citizen_views

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("", citizen_views.home, name="home"),
    path("accounts/", include("accounts.urls")),
    path("citizen/", include("citizen_services.urls")),
    path("operations/", include("workforce.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif getattr(settings, "SERVE_MEDIA", False):
    media_prefix = settings.MEDIA_URL.lstrip("/")
    urlpatterns += [
        re_path(rf"^{media_prefix}(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
