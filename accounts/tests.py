"""Run with:  python manage.py test
Nothing here calls Google, GitHub or Facebook: the network calls are replaced with fakes."""
import io
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, SimpleTestCase, TestCase, override_settings
from PIL import Image

from . import oauth
from .models import Profile, SocialAccount
from .oauth import OAuthError
from .services import resolve_social_user
from .text import clean_block, clean_line, parse_interests

User = get_user_model()
PASSWORD = "Correct-horse-9"

FAKE_PROVIDERS = {
    "google": {"client_id": "gid", "client_secret": "gsecret"},
    "github": {"client_id": "hid", "client_secret": "hsecret"},
    "facebook": {"client_id": "fid", "client_secret": "fsecret"},
}


def png_bytes(size=(40, 30), color=(200, 30, 30)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class TextTests(SimpleTestCase):
    def test_clean_line_and_block(self):
        self.assertEqual(clean_line("  hi\x00 there \n you ", 20), "hi there you")
        self.assertEqual(clean_line("x" * 100, 10), "x" * 10)
        self.assertEqual(clean_block("a\r\n\r\n\r\n\r\nb\x07", 50), "a\n\nb")

    def test_parse_interests(self):
        self.assertEqual(parse_interests("Chess, python ,CHESS;hiking\n"), ["Chess", "python", "hiking"])
        self.assertEqual(len(parse_interests(",".join(str(i) for i in range(50)))), 12)


class SignUpLoginTests(TestCase):
    def setUp(self):
        cache.clear()

    def signup(self, **over):
        data = {"display_name": "Maya", "email": "Maya@Example.com", "password1": PASSWORD, "password2": PASSWORD}
        data.update(over)
        return self.client.post("/accounts/signup/", data)

    def test_pages_load(self):
        for url in ("/accounts/login/", "/accounts/signup/"):
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_signup_creates_account_profile_and_session(self):
        r = self.signup()
        self.assertRedirects(r, "/", fetch_redirect_response=False)
        user = User.objects.get(email="maya@example.com")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)                 # stored hashed
        self.assertEqual(user.profile.display_name, "Maya")
        self.assertEqual(self.client.get("/").status_code, 200)       # signed in right away

    def test_signup_validation_errors(self):
        self.assertEqual(self.signup(email="nope").status_code, 400)
        self.assertEqual(self.signup(password2="different").status_code, 400)
        self.assertEqual(self.signup(password1="12345678", password2="12345678").status_code, 400)
        self.assertEqual(User.objects.count(), 0)

    def test_duplicate_email_is_rejected_case_insensitively(self):
        self.signup()
        self.client.post("/accounts/logout/")
        r = self.signup(email="MAYA@example.com")
        self.assertEqual(r.status_code, 400)
        self.assertContains(r, "already exists", status_code=400)
        self.assertEqual(User.objects.count(), 1)

    def test_login_logout_flow(self):
        self.signup()
        self.client.post("/accounts/logout/")
        self.assertEqual(self.client.get("/").status_code, 302)       # signed out
        r = self.client.post("/accounts/login/", {"email": "MAYA@example.com", "password": PASSWORD})
        self.assertRedirects(r, "/", fetch_redirect_response=False)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.client.post("/accounts/logout/")
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_logout_requires_post(self):
        self.signup()
        self.assertEqual(self.client.get("/accounts/logout/").status_code, 405)

    def test_wrong_password_shows_generic_error(self):
        self.signup()
        self.client.post("/accounts/logout/")
        r = self.client.post("/accounts/login/", {"email": "maya@example.com", "password": "wrong"})
        self.assertContains(r, "don&#x27;t match", status_code=400)
        r = self.client.post("/accounts/login/", {"email": "ghost@example.com", "password": "wrong"})
        self.assertContains(r, "don&#x27;t match", status_code=400)    # same message: no account guessing

    def test_login_is_throttled_after_repeated_failures(self):
        self.signup()
        self.client.post("/accounts/logout/")
        for _ in range(5):
            self.client.post("/accounts/login/", {"email": "maya@example.com", "password": "wrong"})
        r = self.client.post("/accounts/login/", {"email": "maya@example.com", "password": PASSWORD})
        self.assertContains(r, "Too many attempts", status_code=400)

    def test_remember_me_off_ends_session_with_browser(self):
        self.signup()
        self.client.post("/accounts/logout/")
        self.client.post("/accounts/login/", {"email": "maya@example.com", "password": PASSWORD})
        self.assertTrue(self.client.session.get_expire_at_browser_close())
        self.client.post("/accounts/logout/")
        self.client.post("/accounts/login/", {"email": "maya@example.com", "password": PASSWORD, "remember": "on"})
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_next_only_allows_same_site(self):
        self.signup()
        self.client.post("/accounts/logout/")
        r = self.client.post("/accounts/login/", {"email": "maya@example.com", "password": PASSWORD, "next": "https://evil.example/"})
        self.assertRedirects(r, "/", fetch_redirect_response=False)

    def test_signed_in_user_is_sent_away_from_login(self):
        self.signup()
        self.assertEqual(self.client.get("/accounts/login/").status_code, 302)


class ProfileTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("maya", "maya@example.com", PASSWORD)
        self.client.force_login(self.user)

    def post(self, **over):
        data = {"display_name": "Maya Cruz", "bio": "Nursing student", "interests": "chess, python, chess",
                "traits": ["visual", "curious"], "communication_style": "direct", "preferences": "Use analogies",
                "personalize": "on", "use_name": "on", "use_bio": "on", "use_interests": "on",
                "use_traits": "on", "use_style": "on", "use_preferences": "on"}
        data.update(over)
        data = {k: v for k, v in data.items() if v is not None}
        return self.client.post("/accounts/profile/", data)

    def test_profile_page_needs_sign_in(self):
        self.assertEqual(Client().get("/accounts/profile/").status_code, 302)
        self.assertEqual(self.client.get("/accounts/profile/").status_code, 200)

    def test_profile_is_saved_to_the_account(self):
        self.assertRedirects(self.post(), "/accounts/profile/", fetch_redirect_response=False)
        p = Profile.objects.get(user=self.user)
        self.assertEqual((p.display_name, p.bio, p.communication_style), ("Maya Cruz", "Nursing student", "direct"))
        self.assertEqual(p.interests, ["chess", "python"])
        self.assertCountEqual(p.traits, ["visual", "curious"])
        self.assertContains(self.client.get("/accounts/profile/"), "Nursing student")

    def test_switches_are_saved(self):
        self.post(use_bio=None, personalize=None)
        p = Profile.objects.get(user=self.user)
        self.assertFalse(p.use_bio)
        self.assertFalse(p.personalize)
        self.assertTrue(p.use_name)

    def test_invalid_choices_are_rejected(self):
        r = self.post(communication_style="evil", traits=["nope"])
        self.assertEqual(r.status_code, 400)

    def test_avatar_upload_is_resized_and_served_only_to_owner(self):
        up = SimpleUploadedFile("me.png", png_bytes((600, 300)), content_type="image/png")
        self.post(avatar=up)
        p = Profile.objects.get(user=self.user)
        self.assertTrue(p.has_avatar)
        r = self.client.get("/accounts/avatar/")
        self.assertEqual(r["Content-Type"], "image/jpeg")
        img = Image.open(io.BytesIO(r.content))
        self.assertEqual(img.size, (256, 256))
        self.assertEqual(Client().get("/accounts/avatar/").status_code, 302)   # signed-out visitors can't fetch it

    def test_fake_image_is_rejected(self):
        up = SimpleUploadedFile("me.png", b"<script>alert(1)</script>", content_type="image/png")
        r = self.post(avatar=up)
        self.assertContains(r, "valid picture", status_code=400)
        self.assertFalse(Profile.objects.get(user=self.user).has_avatar)

    def test_avatar_can_be_removed(self):
        self.post(avatar=SimpleUploadedFile("me.png", png_bytes(), content_type="image/png"))
        self.post(remove_avatar="on")
        self.assertFalse(Profile.objects.get(user=self.user).has_avatar)

    def test_change_password(self):
        r = self.client.post("/accounts/profile/password/", {"current_password": "bad", "new_password1": "Brand-new-pass7", "new_password2": "Brand-new-pass7"})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/accounts/profile/password/", {"current_password": PASSWORD, "new_password1": "Brand-new-pass7", "new_password2": "Brand-new-pass7"})
        self.assertRedirects(r, "/accounts/profile/", fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Brand-new-pass7"))
        self.assertEqual(self.client.get("/accounts/profile/").status_code, 200)   # still signed in

    def test_oauth_only_user_can_set_a_first_password(self):
        social = User.objects.create_user("sam", "sam@example.com")
        social.set_unusable_password(); social.save()
        self.client.force_login(social)
        r = self.client.post("/accounts/profile/password/", {"new_password1": "Brand-new-pass7", "new_password2": "Brand-new-pass7"})
        self.assertRedirects(r, "/accounts/profile/", fetch_redirect_response=False)
        social.refresh_from_db()
        self.assertTrue(social.has_usable_password())


class OAuthUnitTests(SimpleTestCase):
    @override_settings(OAUTH_PROVIDERS=FAKE_PROVIDERS)
    def test_authorize_urls_and_pkce(self):
        verifier, challenge = oauth.make_pkce()
        url = oauth.authorize_url("google", "http://x/cb", "STATE", challenge)
        q = parse_qs(urlparse(url).query)
        self.assertEqual(q["client_id"], ["gid"])
        self.assertEqual(q["state"], ["STATE"])
        self.assertEqual(q["redirect_uri"], ["http://x/cb"])
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertNotIn("client_secret", url)
        gh = parse_qs(urlparse(oauth.authorize_url("github", "http://x/cb", "S")).query)
        self.assertIn("user:email", gh["scope"][0])
        fb = oauth.authorize_url("facebook", "http://x/cb", "S")
        self.assertIn("facebook.com", fb)
        self.assertIn("email", parse_qs(urlparse(fb).query)["scope"][0])

    @override_settings(OAUTH_PROVIDERS={"google": {"client_id": "a", "client_secret": ""}})
    def test_provider_without_secret_is_not_configured(self):
        self.assertFalse(oauth.is_configured("google"))
        self.assertFalse(oauth.is_configured("github"))


@override_settings(OAUTH_PROVIDERS=FAKE_PROVIDERS)
class OAuthFlowTests(TestCase):
    def info(self, **over):
        data = {"uid": "123", "email": "sam@example.com", "email_verified": True, "name": "Sam Lee", "picture": "https://img.example/a.png"}
        data.update(over)
        return data

    def start(self, provider="google"):
        r = self.client.get(f"/accounts/oauth/{provider}/start/")
        self.assertEqual(r.status_code, 302)
        q = parse_qs(urlparse(r["Location"]).query)
        return q["state"][0]

    def callback(self, provider, state, info=None, **extra):
        params = {"code": "CODE", "state": state}
        params.update(extra)
        with patch("accounts.views.oauth.fetch_identity", return_value=info or self.info()):
            return self.client.get(f"/accounts/oauth/{provider}/callback/", params)

    def test_unknown_provider_is_404(self):
        self.assertEqual(self.client.get("/accounts/oauth/myspace/start/").status_code, 404)

    @override_settings(OAUTH_PROVIDERS={"google": {"client_id": "a", "client_secret": ""}})
    def test_unconfigured_provider_explains_itself(self):
        r = self.client.get("/accounts/oauth/google/start/", follow=True)
        self.assertContains(r, "isn&#x27;t set up yet")

    def test_every_provider_creates_an_account_and_signs_in(self):
        for i, provider in enumerate(("google", "github", "facebook")):
            client = Client()
            self.client = client
            state = self.start(provider)
            info = self.info(uid=str(i), email=f"user{i}@example.com", email_verified=provider != "facebook")
            r = self.callback(provider, state, info)
            self.assertRedirects(r, "/", fetch_redirect_response=False)
            user = User.objects.get(email=f"user{i}@example.com")
            self.assertEqual(user.profile.display_name, "Sam Lee")
            self.assertFalse(user.has_usable_password())
            self.assertTrue(SocialAccount.objects.filter(user=user, provider=provider, uid=str(i)).exists())
            self.assertEqual(client.get("/").status_code, 200)

    def test_second_login_reuses_the_same_user(self):
        self.callback("google", self.start())
        self.client.post("/accounts/logout/")
        self.callback("google", self.start())
        self.assertEqual(User.objects.count(), 1)

    def test_wrong_or_missing_state_is_refused(self):
        self.start()
        r = self.callback("google", "forged")
        self.assertRedirects(r, "/accounts/login/", fetch_redirect_response=False)
        self.assertEqual(User.objects.count(), 0)
        r = self.client.get("/accounts/oauth/google/callback/", {"code": "x", "state": "y"})   # no saved state at all
        self.assertRedirects(r, "/accounts/login/", fetch_redirect_response=False)

    def test_state_cannot_be_reused(self):
        state = self.start()
        self.callback("google", state)
        self.client.post("/accounts/logout/")
        r = self.callback("google", state)
        self.assertRedirects(r, "/accounts/login/", fetch_redirect_response=False)

    def test_user_cancelling_is_handled(self):
        self.start()
        r = self.client.get("/accounts/oauth/google/callback/", {"error": "access_denied"}, follow=True)
        self.assertContains(r, "cancelled")

    def test_provider_failure_shows_message(self):
        state = self.start()
        with patch("accounts.views.oauth.fetch_identity", side_effect=OAuthError("Google is down.")):
            r = self.client.get("/accounts/oauth/google/callback/", {"code": "c", "state": state}, follow=True)
        self.assertContains(r, "Google is down.")

    def test_verified_email_links_to_existing_account(self):
        existing = User.objects.create_user("sam", "sam@example.com", PASSWORD)
        existing.profile.email_verified = True
        existing.profile.save()
        self.callback("google", self.start())
        self.assertEqual(User.objects.count(), 1)
        self.assertTrue(existing.social_accounts.filter(provider="google").exists())
        existing.refresh_from_db()
        self.assertTrue(existing.check_password(PASSWORD))            # a verified owner keeps their password

    def test_linking_to_an_unverified_account_cuts_off_the_old_password(self):
        squatter = User.objects.create_user("sam", "sam@example.com", PASSWORD)   # made without proving the email
        self.callback("google", self.start())
        squatter.refresh_from_db()
        self.assertFalse(squatter.has_usable_password())
        self.assertTrue(squatter.profile.email_verified)

    def test_unverified_email_never_links_to_existing_account(self):
        User.objects.create_user("sam", "sam@example.com", PASSWORD)
        info = self.info(email_verified=False)
        with self.assertRaises(OAuthError):
            resolve_social_user("facebook", info)
        self.assertEqual(SocialAccount.objects.count(), 0)

    def test_missing_email_is_explained(self):
        with self.assertRaises(OAuthError):
            resolve_social_user("facebook", self.info(email=""))

    def test_disabled_account_cannot_sign_in(self):
        u = User.objects.create_user("sam", "sam@example.com", PASSWORD, is_active=False)
        SocialAccount.objects.create(user=u, provider="google", uid="123")
        with self.assertRaises(OAuthError):
            resolve_social_user("google", self.info())

    def test_login_page_lists_only_configured_providers_when_not_debug(self):
        with override_settings(DEBUG=False, OAUTH_PROVIDERS={**FAKE_PROVIDERS, "facebook": {"client_id": "", "client_secret": ""}}):
            r = self.client.get("/accounts/login/")
        self.assertContains(r, "/accounts/oauth/google/start/")
        self.assertContains(r, "/accounts/oauth/github/start/")
        self.assertNotContains(r, "/accounts/oauth/facebook/start/")
