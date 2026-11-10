from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = username or kwargs.get("email")
        if not email or not password:
            return None
        user_model = get_user_model()
        user = user_model.objects.filter(email__iexact=email).first()
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
