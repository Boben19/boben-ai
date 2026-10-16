"""OAuth 2.0 "authorization code" login for Google, GitHub and Facebook.

Everything here runs on the server. Client secrets are only read from settings (which read the
environment) and are only ever sent to the provider's token endpoint, never to the browser.
"""
import base64
import hashlib
import secrets
from urllib.parse import urlencode

import requests
from django.conf import settings

TIMEOUT = 10


class OAuthError(Exception):
    """A problem with a message that is safe to show to the user."""


def _facebook_base():
    return "https://graph.facebook.com/" + settings.FACEBOOK_GRAPH_VERSION


PROVIDERS = {
    "google": {
        "label": "Google",
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "scope": "openid email profile",
        "pkce": True,
    },
    "github": {
        "label": "GitHub",
        "authorize": "https://github.com/login/oauth/authorize",
        "scope": "read:user user:email",
        "pkce": False,
    },
    "facebook": {
        "label": "Facebook",
        "authorize": "https://www.facebook.com/" + settings.FACEBOOK_GRAPH_VERSION + "/dialog/oauth",
        "scope": "email,public_profile",
        "pkce": False,
    },
}


def label(provider):
    return PROVIDERS[provider]["label"]


def credentials(provider):
    cfg = settings.OAUTH_PROVIDERS.get(provider, {})
    return cfg.get("client_id", ""), cfg.get("client_secret", "")


def is_configured(provider):
    cid, secret = credentials(provider)
    return provider in PROVIDERS and bool(cid and secret)


ENV_NAMES = {
    "google": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
    "github": ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"),
    "facebook": ("FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET"),
}


def missing_settings(provider):
    """Names of the environment variables that are still empty for this provider (for the setup hint)."""
    cid, secret = credentials(provider)
    id_name, secret_name = ENV_NAMES[provider]
    missing = [name for name, value in ((id_name, cid), (secret_name, secret)) if not value]
    return " and ".join(missing) or "its keys"


def make_pkce():
    """Returns (verifier, challenge) for the S256 method."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorize_url(provider, redirect_uri, state, code_challenge=None):
    client_id, _ = credentials(provider)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": PROVIDERS[provider]["scope"],
        "state": state,
    }
    if provider == "google":
        params["prompt"] = "select_account"
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"
    return PROVIDERS[provider]["authorize"] + "?" + urlencode(params)


def _json(resp, provider):
    try:
        return resp.json()
    except ValueError:
        raise OAuthError("%s sent a reply we couldn't read. Please try again." % label(provider))


def _get(url, provider, **kwargs):
    try:
        return requests.get(url, timeout=TIMEOUT, **kwargs)
    except requests.exceptions.RequestException:
        raise OAuthError("We couldn't reach %s. Please try again in a moment." % label(provider))


def _post(url, provider, **kwargs):
    try:
        return requests.post(url, timeout=TIMEOUT, **kwargs)
    except requests.exceptions.RequestException:
        raise OAuthError("We couldn't reach %s. Please try again in a moment." % label(provider))


def _token(provider, code, redirect_uri, code_verifier):
    client_id, client_secret = credentials(provider)
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
    }
    if provider == "google":
        data["grant_type"] = "authorization_code"
        if code_verifier:
            data["code_verifier"] = code_verifier
        resp = _post("https://oauth2.googleapis.com/token", provider, data=data)
    elif provider == "github":
        resp = _post("https://github.com/login/oauth/access_token", provider, data=data,
                     headers={"Accept": "application/json"})
    else:  # facebook
        resp = _get(_facebook_base() + "/oauth/access_token", provider, params=data)

    body = _json(resp, provider)
    token = body.get("access_token") if isinstance(body, dict) else None
    if resp.status_code != 200 or not token:
        raise OAuthError("%s didn't accept the sign-in. Please try again." % label(provider))
    return token


def _fetch_google(token):
    resp = _get("https://openidconnect.googleapis.com/v1/userinfo", "google",
                headers={"Authorization": "Bearer " + token})
    data = _json(resp, "google")
    if resp.status_code != 200 or not data.get("sub"):
        raise OAuthError("Google didn't share your profile. Please try again.")
    return {
        "uid": str(data["sub"]),
        "email": (data.get("email") or "").strip().lower(),
        "email_verified": data.get("email_verified") is True,
        "name": data.get("name") or "",
        "picture": data.get("picture") or "",
    }


def _fetch_github(token):
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28"}
    resp = _get("https://api.github.com/user", "github", headers=headers)
    data = _json(resp, "github")
    if resp.status_code != 200 or not data.get("id"):
        raise OAuthError("GitHub didn't share your profile. Please try again.")

    # The public profile email can be empty or unverified, so ask for the verified list.
    email, verified = "", False
    resp = _get("https://api.github.com/user/emails", "github", headers=headers)
    if resp.status_code == 200:
        emails = _json(resp, "github")
        if isinstance(emails, list):
            good = [e for e in emails if isinstance(e, dict) and e.get("verified") and e.get("email")]
            primary = [e for e in good if e.get("primary")]
            pick = (primary or good or [None])[0]
            if pick:
                email, verified = pick["email"].strip().lower(), True
    return {
        "uid": str(data["id"]),
        "email": email,
        "email_verified": verified,
        "name": data.get("name") or data.get("login") or "",
        "picture": data.get("avatar_url") or "",
    }


def _fetch_facebook(token):
    resp = _get(_facebook_base() + "/me", "facebook",
                params={"fields": "id,name,email,picture.type(large)", "access_token": token})
    data = _json(resp, "facebook")
    if resp.status_code != 200 or not data.get("id"):
        raise OAuthError("Facebook didn't share your profile. Please try again.")
    picture = ((data.get("picture") or {}).get("data") or {}).get("url") or ""
    return {
        "uid": str(data["id"]),
        # Facebook does not promise that the email is verified, so we never treat it as verified.
        "email": (data.get("email") or "").strip().lower(),
        "email_verified": False,
        "name": data.get("name") or "",
        "picture": picture,
    }


_FETCHERS = {"google": _fetch_google, "github": _fetch_github, "facebook": _fetch_facebook}


def fetch_identity(provider, code, redirect_uri, code_verifier=None):
    """Trade the one-time code for the person's identity: {uid, email, email_verified, name, picture}."""
    token = _token(provider, code, redirect_uri, code_verifier)
    return _FETCHERS[provider](token)
