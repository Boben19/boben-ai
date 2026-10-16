import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import oauth
from .avatars import AvatarError, process_avatar
from .forms import LoginForm, PasswordForm, ProfileForm, SignUpForm
from .models import COMMUNICATION_STYLES, TRAIT_CHOICES
from .services import create_local_user, resolve_social_user, safe_next, sync_provider_picture

BACKEND = "accounts.backends.EmailBackend"
FAIL_LIMIT, FAIL_WINDOW = 5, 5 * 60          # 5 wrong passwords per 5 minutes (per address + email)


def _provider_buttons():
    """Providers to show on the sign-in pages. Not-yet-configured ones only appear while DEBUG is on."""
    out = []
    for key in ("google", "github", "facebook"):
        ready = oauth.is_configured(key)
        if ready or settings.DEBUG:
            out.append({"key": key, "label": oauth.label(key), "ready": ready})
    return out


def _auth_context(request, **extra):
    ctx = {"providers": _provider_buttons(), "next": request.GET.get("next") or request.POST.get("next") or ""}
    ctx.update(extra)
    return ctx


def _callback_uri(request, provider):
    path = reverse("accounts:oauth_callback", args=[provider])
    return (settings.SITE_URL + path) if settings.SITE_URL else request.build_absolute_uri(path)


def _fail_key(request, email):
    return "loginfail:%s:%s" % (request.META.get("REMOTE_ADDR", ""), email.strip().lower()[:254])


# ---------------------------------------------------------------- email sign-up / sign-in / sign-out
@never_cache
@require_http_methods(["GET", "POST"])
def signup(request):
    if request.user.is_authenticated:
        return redirect("index")
    form = SignUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = create_local_user(form.cleaned_data["email"], form.cleaned_data["password1"], form.cleaned_data["display_name"])
        login(request, user, backend=BACKEND)
        messages.success(request, "Welcome to Boben! Your account is ready.")
        return redirect(safe_next(request, request.POST.get("next"), settings.LOGIN_REDIRECT_URL))
    return render(request, "accounts/signup.html", _auth_context(request, form=form), status=400 if form.errors else 200)


@never_cache
@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("index")
    form = LoginForm(request.POST or None)
    error = ""
    if request.method == "POST" and form.is_valid():
        email, password = form.cleaned_data["email"], form.cleaned_data["password"]
        key = _fail_key(request, email)
        if cache.get(key, 0) >= FAIL_LIMIT:
            error = "Too many attempts. Please wait a few minutes and try again."
        else:
            user = authenticate(request, username=email, password=password)
            if user is not None:
                cache.delete(key)
                login(request, user, backend=BACKEND)
                if not form.cleaned_data["remember"]:
                    request.session.set_expiry(0)            # ends when the browser closes
                return redirect(safe_next(request, request.POST.get("next"), settings.LOGIN_REDIRECT_URL))
            cache.set(key, cache.get(key, 0) + 1, FAIL_WINDOW)
            error = "That email and password don't match. If you signed up with Google, GitHub or Facebook, use that button instead."
    status = 400 if (form.errors or error) else 200
    return render(request, "accounts/login.html", _auth_context(request, form=form, error=error), status=status)


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "You're signed out.")
    return redirect("accounts:login")


# ---------------------------------------------------------------- OAuth
@never_cache
@require_GET
def oauth_start(request, provider):
    if provider not in oauth.PROVIDERS:
        raise Http404
    if not oauth.is_configured(provider):
        msg = "%s sign-in isn't set up yet." % oauth.label(provider)
        if settings.DEBUG:
            msg += " Add %s to your .env file and restart the server (see README)." % oauth.missing_settings(provider)
        messages.error(request, msg)
        return redirect("accounts:login")
    state = secrets.token_urlsafe(32)
    verifier = challenge = None
    if oauth.PROVIDERS[provider]["pkce"]:
        verifier, challenge = oauth.make_pkce()
    request.session["oauth"] = {
        "provider": provider, "state": state, "verifier": verifier,
        "next": safe_next(request, request.GET.get("next"), settings.LOGIN_REDIRECT_URL),
    }
    return redirect(oauth.authorize_url(provider, _callback_uri(request, provider), state, challenge))


@never_cache
@require_GET
def oauth_callback(request, provider):
    if provider not in oauth.PROVIDERS:
        raise Http404
    saved = request.session.pop("oauth", None)                 # one-time use
    name = oauth.label(provider)

    if request.GET.get("error"):
        messages.error(request, "You cancelled the %s sign-in, or %s refused it. Nothing was changed." % (name, name))
        return redirect("accounts:login")
    if not saved or saved.get("provider") != provider or not secrets.compare_digest(
        str(saved.get("state", "")), request.GET.get("state", "")
    ):
        messages.error(request, "That sign-in link expired or didn't match. Please start again.")
        return redirect("accounts:login")
    code = request.GET.get("code", "")
    if not code:
        messages.error(request, "%s didn't send back a sign-in code. Please try again." % name)
        return redirect("accounts:login")

    try:
        info = oauth.fetch_identity(provider, code, _callback_uri(request, provider), saved.get("verifier"))
        user, created = resolve_social_user(provider, info)
    except oauth.OAuthError as err:
        messages.error(request, str(err))
        return redirect("accounts:login")

    sync_provider_picture(user, info)
    login(request, user, backend=BACKEND)
    messages.success(request, ("Welcome to Boben!" if created else "Welcome back!"))
    return redirect(saved.get("next") or settings.LOGIN_REDIRECT_URL)


# ---------------------------------------------------------------- profile
PERSONALIZATION_TOGGLES = [
    ("use_name", "My name", "Boben may call you by your first name."),
    ("use_bio", "My bio", "Background about you."),
    ("use_interests", "My interests", "Examples and analogies can match what you like."),
    ("use_traits", "My personality traits", "Explanations can fit how you think and learn."),
    ("use_style", "My communication style", "The tone Boben replies in."),
    ("use_preferences", "My preferences", "Your own notes about how you like answers."),
]


def _profile_initial(profile):
    return {
        "display_name": profile.display_name, "bio": profile.bio, "communication_style": profile.communication_style,
        "preferences": profile.preferences, "personalize": profile.personalize, "use_name": profile.use_name,
        "use_bio": profile.use_bio, "use_interests": profile.use_interests, "use_traits": profile.use_traits,
        "use_style": profile.use_style, "use_preferences": profile.use_preferences,
    }


def _profile_context(request, form, pw_form=None, pw_open=False):
    profile = request.user.profile
    if form.is_bound:
        selected = set(form.data.getlist("traits"))
        interests_text = form.data.get("interests", "")
    else:
        selected = set(profile.traits)
        interests_text = ", ".join(profile.interests)
    return {
        "profile": profile,
        "form": form,
        "pw_form": pw_form or PasswordForm(user=request.user),
        "pw_open": pw_open or bool(pw_form and pw_form.errors),
        "traits": [{"key": k, "label": v, "checked": k in selected} for k, v in TRAIT_CHOICES],
        "styles": COMMUNICATION_STYLES,
        "interests_text": interests_text,
        "has_password": request.user.has_usable_password(),
        "linked": [oauth.label(s.provider) for s in request.user.social_accounts.all() if s.provider in oauth.PROVIDERS],
        "toggles": [
            {"key": key, "title": title, "hint": hint, "checked": bool(form[key].value())}
            for key, title, hint in PERSONALIZATION_TOGGLES
        ],
    }


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def profile_view(request):
    profile = request.user.profile
    if request.method == "GET":
        return render(request, "accounts/profile.html", _profile_context(request, ProfileForm(initial=_profile_initial(profile))))

    form = ProfileForm(request.POST, request.FILES)
    new_avatar = None
    if form.is_valid() and request.FILES.get("avatar"):
        try:
            new_avatar = process_avatar(request.FILES["avatar"])
        except AvatarError as err:
            form.add_error("avatar", str(err))
    if not form.is_valid() or form.errors:
        return render(request, "accounts/profile.html", _profile_context(request, form), status=400)

    d = form.cleaned_data
    profile.display_name = d["display_name"]
    profile.bio = d["bio"]
    profile.interests = d["interests"]
    profile.traits = [t for t in d["traits"]]
    profile.communication_style = d["communication_style"]
    profile.preferences = d["preferences"]
    for flag in ("personalize", "use_name", "use_bio", "use_interests", "use_traits", "use_style", "use_preferences"):
        setattr(profile, flag, d[flag])
    if new_avatar:
        profile.avatar_data, profile.avatar_type = new_avatar, "image/jpeg"
        profile.avatar_version += 1
    elif d["remove_avatar"] and profile.has_avatar:
        profile.avatar_data, profile.avatar_type = None, ""
        profile.avatar_version += 1
    profile.save()
    messages.success(request, "Profile saved.")
    return redirect("accounts:profile")


@never_cache
@login_required
@require_POST
def password_view(request):
    form = PasswordForm(request.POST, user=request.user)
    if form.is_valid():
        request.user.set_password(form.cleaned_data["new_password1"])
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)           # keeps this browser signed in
        messages.success(request, "Password updated.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html",
                  _profile_context(request, ProfileForm(initial=_profile_initial(request.user.profile)), form, True),
                  status=400)


@login_required
@require_GET
def avatar_view(request):
    """Your own profile picture. Only the signed-in owner can fetch it."""
    profile = request.user.profile
    if not profile.has_avatar:
        raise Http404
    resp = HttpResponse(bytes(profile.avatar_data), content_type=profile.avatar_type or "image/jpeg")
    resp["Cache-Control"] = "private, max-age=86400"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp
