"""
Talks to the Google Gemini REST API.

This file is the ONLY place that uses the API key, and it only runs on the
server, so the key never reaches the browser.
"""
import requests

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# The personality lives here, on the server, so users can't edit it.
SYSTEM_INSTRUCTION = """You are Boben AI, a personal AI assistant with a green clover mascot.

Personality:
- Friendly and sociable: talk like a helpful friend who is easy to approach.
- Witty: use light humor and playful remarks when it fits. Never force jokes into serious topics.
- Smart but approachable: explain hard ideas (programming, technology, academics) in simple words, with small examples.
- Supportive and encouraging: help people study, brainstorm, solve problems, plan tasks, and feel confident.
- Honest and straightforward: be accurate, say so when you are unsure, and never pretend to know everything.
- Respectful and mature: switch to a calm, professional tone for schoolwork, leadership, formal writing, or sensitive topics.

Style rules:
- Sound natural and human, not like a corporate chatbot or customer-service script.
- Use simple English. Match the user's language and tone when appropriate.
- Keep answers short by default. Go deeper only when the user needs it or asks for it.
- Do not start every reply with a greeting. Avoid robotic phrases and generic motivational quotes.
- Use emojis sparingly (at most one or two, and only when they fit).
- Use short paragraphs and simple lists. Put code in fenced code blocks.
"""


class GeminiError(Exception):
    """An error with a message that is safe to show to the user."""

    def __init__(self, message, status=502):
        super().__init__(message)
        self.message = message
        self.status = status


def build_contents(history, prompt):
    """Turn our chat history + new prompt into Gemini's 'contents' format.

    history: list of {"role": "user" | "assistant", "text": "..."}
    Gemini uses the role names "user" and "model".
    """
    contents = []
    for item in history:
        role = "user" if item["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": item["text"]}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    return contents


def ask_gemini(api_key, model, history, prompt, timeout=30):
    """Send the conversation to Gemini and return the reply text."""
    if not api_key:
        raise GeminiError(
            "Boben AI isn't set up yet. Add GEMINI_API_KEY to the .env file and restart the server.",
            status=500,
        )

    payload = {
        "system_instruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": build_contents(history, prompt),
        "generationConfig": {"temperature": 0.8, "maxOutputTokens": 1024},
    }
    # The key goes in a header, never in the URL, so it can't leak into logs.
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    try:
        resp = requests.post(
            API_URL.format(model=model), json=payload, headers=headers, timeout=timeout
        )
    except requests.exceptions.Timeout:
        raise GeminiError("Gemini took too long to answer. Please try again.", status=504)
    except requests.exceptions.RequestException:
        raise GeminiError(
            "I couldn't reach Gemini. Check your internet connection and try again.", status=502
        )

    if resp.status_code == 429:
        raise GeminiError(
            "I've hit the free-tier limit for now. Wait a minute and try again.", status=429
        )
    if resp.status_code in (400, 401, 403):
        # Don't echo Google's raw error (it may mention the key).
        raise GeminiError(
            "Gemini rejected the request. Check that your API key and model name are valid.",
            status=502,
        )
    if resp.status_code == 404:
        raise GeminiError(
            "That Gemini model wasn't found. Check GEMINI_MODEL in your .env file.", status=502
        )
    if resp.status_code >= 500:
        raise GeminiError("Gemini is having a bad moment. Please try again shortly.", status=502)
    if resp.status_code != 200:
        raise GeminiError("Something unexpected happened with Gemini. Please try again.", status=502)

    try:
        data = resp.json()
    except ValueError:
        raise GeminiError("Gemini sent back something I couldn't read.", status=502)

    if data.get("promptFeedback", {}).get("blockReason"):
        raise GeminiError("I can't help with that one. Try asking in a different way.", status=422)

    try:
        parts = data["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except (KeyError, IndexError, TypeError):
        text = ""

    if not text:
        raise GeminiError("I didn't get an answer back. Please try rephrasing.", status=502)
    return text
