import uuid

from django.conf import settings
from django.contrib.auth import logout
from django.utils import timezone

_DEVELOPMENT_SERVER_INSTANCE = uuid.uuid4().hex


class DevelopmentServerSessionResetMiddleware:
    session_key = "_development_server_instance"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEVELOPMENT_SERVER_SESSION_RESET:
            previous_instance = request.session.get(self.session_key)
            if previous_instance and previous_instance != _DEVELOPMENT_SERVER_INSTANCE:
                if request.session.get("_auth_user_id"):
                    request.session.flush()
            request.session[self.session_key] = _DEVELOPMENT_SERVER_INSTANCE
        return self.get_response(request)


class InactiveSessionTimeoutMiddleware:
    timeout_seconds = 30 * 60

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            now = int(timezone.now().timestamp())
            last_activity = request.session.get("last_activity")
            if last_activity and now - last_activity > self.timeout_seconds:
                logout(request)
            if request.user.is_authenticated:
                request.session["last_activity"] = now
                request.session.set_expiry(self.timeout_seconds)
        return self.get_response(request)
