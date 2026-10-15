"""
Talks to the Google Gemini REST API.

This file is the ONLY place that uses the API key, and it only runs on the
server, so the key never reaches the browser.
"""
import time

import requests

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# The personality lives here, on the server, so users can't edit it.
SYSTEM_INSTRUCTION = """You are Boben, a personal study partner and everyday helper. Your mascot is a green clover.

Personality:
- Friendly and easy to talk to, like a classmate who happens to be really good at explaining things.
- Light humor when it fits. Never force a joke into a serious topic.
- Smart but approachable: explain hard ideas (programming, technology, academics) in plain words, with small examples.
- Encouraging and practical: help people study, brainstorm, solve problems, plan their time, and feel confident.
- Honest: be accurate, say so when you are unsure, and never pretend to know everything.
- Calm and professional for schoolwork, formal writing, leadership, or sensitive topics.

Style rules:
- Sound natural and human. No corporate or customer-service phrasing.
- Never describe yourself with labels like "AI", "language model" or "chatbot", and never mention who built or trained you, unless the person sincerely asks. If someone sincerely asks whether they are talking to a person or a program, tell them the truth in one short sentence: you are a program.
- Use simple English. Match the person's language and tone when appropriate.
- Do not start every reply with a greeting. Skip generic motivational quotes.
- Use emojis rarely (at most one, and only when it really fits).
- Use short paragraphs and simple lists. Put code in fenced code blocks with the language name.
"""

# What each mode adds on top of the personality.
MODE_NOTES = {
    "chat": "",
    "study": "Mode: Study. Teach step by step. Start with the core idea in one or two sentences, then a small example. When it helps, end with a quick question the person can use to test themselves.",
    "code": "Mode: Code. Be precise. Show working code in fenced blocks, explain what each important part does, and point out common mistakes. Ask for the error message if it is missing.",
    "write": "Mode: Write. Help with drafting, rewriting and proofreading. Keep the person's own voice, make it sound natural and clear, and give the improved text first, then a short note on what changed.",
    "plan": "Mode: Plan. Turn messy goals into a realistic plan: priorities first, then a short ordered list with rough time estimates. Be honest about what is too much for the time available.",
}
LENGTH_NOTES = {
    "short": "Keep replies very short: a few sentences unless the person asks for more.",
    "balanced": "Keep replies concise by default. Go deeper only when the question needs it.",
    "detailed": "Give thorough, well-organized answers with examples when they help.",
}
LENGTH_TOKENS = {"short": 800, "balanced": 1500, "detailed": 3000}


def build_system_instruction(mode="chat", length="balanced", name=""):
    """Personality + the person's current mode, reply length and (optional) first name."""
    parts = [SYSTEM_INSTRUCTION.strip()]
    if MODE_NOTES.get(mode):
        parts.append(MODE_NOTES[mode])
    parts.append(LENGTH_NOTES.get(length, LENGTH_NOTES["balanced"]))
    if name:
        parts.append(f"The person's first name is {name}. Use it only now and then, never in every reply.")
    return "\n\n".join(parts)


class GeminiError(Exception):
    """An error with a message that is safe to show to the user.

    try_next_model=True means "this model has a problem (busy, missing, rate-limited),
    so another model might still work".
    """

    def __init__(self, message, status=502, try_next_model=False):
        super().__init__(message)
        self.message = message
        self.status = status
        self.try_next_model = try_next_model


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


def _call_model(api_key, model, payload, timeout):
    """Ask ONE model. Returns the reply text or raises GeminiError."""
    # The key goes in a header, never in the URL, so it can't leak into logs.
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    resp = None
    for attempt in range(2):  # one quick retry for short hiccups
        try:
            resp = requests.post(
                API_URL.format(model=model), json=payload, headers=headers, timeout=timeout
            )
        except requests.exceptions.Timeout:
            raise GeminiError("That took too long. Please try again.", status=504, try_next_model=True)
        except requests.exceptions.RequestException:
            raise GeminiError(
                "I couldn't connect just now. Check your internet and try again.", status=502
            )
        if resp.status_code in (500, 502, 503, 504) and attempt == 0:
            time.sleep(1.5)
            continue
        break

    if resp.status_code != 200:
        # Print Google's real explanation in the server terminal (never shown to the user).
        body = resp.text[:600].replace(api_key, "<hidden>") if hasattr(resp, "text") else ""
        print(f"[Boben] Gemini returned HTTP {resp.status_code} for model '{model}': {body}", flush=True)

    if resp.status_code == 429:
        raise GeminiError(
            "I've hit the free-tier limit for now. Wait a minute and try again.", status=429, try_next_model=True
        )
    if resp.status_code in (400, 401, 403):
        # Don't echo Google's raw error (it may mention the key).
        raise GeminiError(
            "Something is off with the setup (API key or model name). Check the .env file.", status=502
        )
    if resp.status_code == 404:
        raise GeminiError(
            "That model wasn't found. Check GEMINI_MODEL in your .env file.", status=502, try_next_model=True
        )
    if resp.status_code >= 500:
        raise GeminiError(
            "I'm a bit swamped right now (error %d). Give it a minute and try again." % resp.status_code,
            status=502,
            try_next_model=True,
        )
    if resp.status_code != 200:
        raise GeminiError("Something unexpected happened. Please try again.", status=502)

    try:
        data = resp.json()
    except ValueError:
        raise GeminiError("I got a reply I couldn't read. Please try again.", status=502)

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


def ask_gemini(api_key, models, history, prompt, timeout=30, mode="chat", length="balanced", name=""):
    """Send the conversation to Gemini and return the reply text.

    `models` is a model name or a list of names. If one model is busy, missing or
    rate-limited, we automatically try the next one in the list.
    """
    if not api_key:
        raise GeminiError(
            "Boben isn't set up yet. Add GEMINI_API_KEY to the .env file and restart the server.",
            status=500,
        )
    if isinstance(models, str):
        models = [models]

    payload = {
        "system_instruction": {"parts": [{"text": build_system_instruction(mode, length, name)}]},
        "contents": build_contents(history, prompt),
        "generationConfig": {
            "temperature": 0.8,
            "maxOutputTokens": LENGTH_TOKENS.get(length, LENGTH_TOKENS["balanced"]),
        },
    }

    last_error = None
    for i, model in enumerate(models):
        try:
            text = _call_model(api_key, model, payload, timeout)
            if i > 0:
                print(f"[Boben] Answered using backup model '{model}'.", flush=True)
            return text
        except GeminiError as err:
            last_error = err
            if not err.try_next_model:
                raise
    raise last_error
