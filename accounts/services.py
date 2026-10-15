"""Account logic that is shared by the email sign-up and the OAuth callback."""
import re

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils.http import url_has_allowed_host_and_scheme

from .models import Profile, SocialAccount
from .oauth import OAuthError, label
from .text import clean_line

User = get_user_model()


def safe_next(request, value, fallback="/"):
    """Only allow redirects back to this same site (blocks open-redirect tricks)."""
    if value and url_has_allowed_host_and_scheme(
        value, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return value
    return fallback


def unique_username(email):
    base = re.sub(r"[^\w.@+-]", "", email.split("@")[0])[:30] or "user"
    candidate, n = base, 1
    while User.objects.filter(username__iexact=candidate).exists():
        n += 1
        candidate = f"{base}{n}"
    return candidate


def create_local_user(email, password, display_name=""):
    email = email.strip().lower()
    with transaction.atomic():
        user = User(username=unique_username(email), email=email)
        user.set_password(password)
        user.save()
        profile = user.profile                      # created by the post_save signal
        profile.display_name = display_name
        profile.save(update_fields=["display_name"])
    return user


def _link(user, provider, uid):
    SocialAccount.objects.create(user=user, provider=provider, uid=uid)


def resolve_social_user(provider, info):
    """Find, link or create the user for a verified OAuth identity. Returns (user, created).

    Raises OAuthError with a friendly message when the sign-in can't be completed safely.
    """
    uid, email = info["uid"], info["email"]
    with transaction.atomic():
        link = SocialAccount.objects.select_related("user", "user__profile").filter(provider=provider, uid=uid).first()
        if link:
            user = link.user
            if not user.is_active:
                raise OAuthError("This account has been disabled.")
            return user, False

        if not email:
            raise OAuthError(
                "%s didn't share an email address, and we need one to create your account. "
                "Add a verified email in your %s settings and try again, or sign up with email." % (label(provider), label(provider))
            )

        existing = User.objects.select_related("profile").filter(email__iexact=email).first()
        if existing:
            if not info["email_verified"]:
                raise OAuthError(
                    "An account with %s already exists. Sign in with your email and password, "
                    "or use Google or GitHub." % email
                )
            if not existing.is_active:
                raise OAuthError("This account has been disabled.")
            profile = existing.profile
            if not profile.email_verified:
                # The existing account was made without proving the email is theirs. Now that a provider
                # has proven it, cut off any other way into the account (pre-hijacking protection).
                existing.set_unusable_password()
                existing.social_accounts.all().delete()
                profile.email_verified = True
                existing.save(update_fields=["password"])
                profile.save(update_fields=["email_verified"])
            _link(existing, provider, uid)
            return existing, False

        try:
            user = User(username=unique_username(email), email=email, is_active=True)
            user.set_unusable_password()
            user.save()
        except IntegrityError:
            raise OAuthError("We couldn't create your account. Please try again.")
        profile = user.profile
        profile.display_name = clean_line(info.get("name"), 60)
        profile.email_verified = bool(info["email_verified"])
        picture = info.get("picture") or ""
        if picture.startswith("https://"):
            profile.avatar_url = picture[:500]
        profile.save()
        _link(user, provider, uid)
        return user, True


def sync_provider_picture(user, info):
    """Use the provider's picture only if the user has not set their own."""
    profile = user.profile
    picture = info.get("picture") or ""
    if picture.startswith("https://") and not profile.has_avatar and profile.avatar_url != picture[:500]:
        profile.avatar_url = picture[:500]
        profile.save(update_fields=["avatar_url"])
