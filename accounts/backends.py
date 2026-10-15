from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Sign in with an email address (case-insensitive). A username also works, for accounts made with `createsuperuser`."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if not username or not password:
            return None
        user = User.objects.filter(email__iexact=username.strip()).first() or \
            User.objects.filter(username__iexact=username.strip()).first()
        if user is None:
            User().set_password(password)      # keeps timing similar whether or not the account exists
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
