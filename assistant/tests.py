"""Run with:  python manage.py test
These tests never call the real Gemini API (it is replaced with a fake)."""
import json
from unittest.mock import patch

from django.test import Client, SimpleTestCase, override_settings

from .gemini import GeminiError


class ChatEndpointTests(SimpleTestCase):
    def post(self, payload, client=None):
        client = client or self.client
        return client.post("/api/chat/", data=json.dumps(payload), content_type="application/json")

    def test_pages_and_pwa_files_load(self):
        for url in ("/", "/offline/", "/manifest.json", "/serviceworker.js"):
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get("/serviceworker.js")["Service-Worker-Allowed"], "/")

    def test_rejects_empty_message(self):
        self.assertEqual(self.post({"message": "   "}).status_code, 400)

    def test_rejects_too_long_message(self):
        self.assertEqual(self.post({"message": "a" * 5000}).status_code, 400)

    def test_rejects_bad_json(self):
        r = self.client.post("/api/chat/", data="not json", content_type="application/json")
        self.assertEqual(r.status_code, 400)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get("/api/chat/").status_code, 405)

    def test_csrf_is_enforced(self):
        strict = Client(enforce_csrf_checks=True)
        self.assertEqual(self.post({"message": "hi"}, client=strict).status_code, 403)

    @patch("assistant.views.ask_gemini", return_value="Hello!")
    def test_success_and_history_cleanup(self, fake):
        history = [{"role": "assistant", "text": "orphan"}, {"role": "user", "text": "q"}, {"role": "bad", "text": "x"}]
        r = self.post({"message": "hi", "history": history})
        self.assertEqual(r.json(), {"reply": "Hello!"})
        sent_history = fake.call_args.args[2]
        self.assertEqual(sent_history, [{"role": "user", "text": "q"}])  # starts with a user turn, bad items dropped

    @patch("assistant.views.ask_gemini", side_effect=GeminiError("Slow down!", status=429))
    def test_gemini_error_is_passed_on(self, _fake):
        r = self.post({"message": "hi"})
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json()["error"], "Slow down!")

    @override_settings(GEMINI_API_KEY="")
    def test_missing_key_gives_friendly_error(self):
        r = self.post({"message": "hi"})
        self.assertEqual(r.status_code, 500)
        self.assertIn("GEMINI_API_KEY", r.json()["error"])

    @patch("assistant.views.ask_gemini", return_value="ok")
    def test_mode_length_and_name_are_passed_and_cleaned(self, fake):
        self.post({"message": "hi", "mode": "study", "length": "short", "name": "Jhon <script>"})
        kwargs = fake.call_args.kwargs
        self.assertEqual(kwargs["mode"], "study")
        self.assertEqual(kwargs["length"], "short")
        self.assertEqual(kwargs["name"], "Jhon script")  # angle brackets removed

    @patch("assistant.views.ask_gemini", return_value="ok")
    def test_unknown_mode_and_length_fall_back(self, fake):
        self.post({"message": "hi", "mode": "hack", "length": "huge", "name": 123})
        kwargs = fake.call_args.kwargs
        self.assertEqual((kwargs["mode"], kwargs["length"], kwargs["name"]), ("chat", "balanced", ""))


class PersonaTests(SimpleTestCase):
    def test_persona_never_labels_itself_as_ai_by_default(self):
        from .gemini import build_system_instruction
        text = build_system_instruction("code", "detailed", "Maya")
        self.assertIn("Mode: Code", text)
        self.assertIn("Maya", text)
        self.assertIn("you are a program", text)  # still honest if someone sincerely asks
