import json
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .gemini import GeminiError, ask_gemini


@ensure_csrf_cookie
@require_GET
def index(request):
    """The chat page. ensure_csrf_cookie makes sure the browser gets a CSRF cookie."""
    return render(request, "assistant/index.html")


@require_GET
def offline(request):
    """Shown by the service worker when a page can't be loaded offline."""
    return render(request, "assistant/offline.html")


@require_GET
def service_worker(request):
    """
    Serve the service worker from the site root ("/serviceworker.js").

    A service worker can only control pages inside its own folder, so it must
    NOT be served from /static/. We read the file from static and send it
    from "/" with the right headers.
    """
    sw_path = Path(__file__).resolve().parent / "static" / "assistant" / "js" / "serviceworker.js"
    response = HttpResponse(sw_path.read_text(encoding="utf-8"), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


@require_POST
def chat(request):
    """
    POST /api/chat/
    Body: {"message": "...", "history": [{"role": "user"|"assistant", "text": "..."}]}
    Returns: {"reply": "..."} or {"error": "..."}
    CSRF is checked automatically by Django's middleware.
    """
    try:
        body = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "That request looked broken. Please try again."}, status=400)

    if not isinstance(body, dict):
        return JsonResponse({"error": "That request looked broken. Please try again."}, status=400)

    # ---- validate the new message ----
    message = body.get("message")
    if not isinstance(message, str) or not message.strip():
        return JsonResponse({"error": "Type a message first and I'll jump in."}, status=400)
    message = message.strip()
    if len(message) > settings.MAX_PROMPT_CHARS:
        return JsonResponse(
            {"error": f"That message is too long. Please keep it under {settings.MAX_PROMPT_CHARS} characters."},
            status=400,
        )

    # ---- validate and trim the history ----
    history = []
    raw_history = body.get("history", [])
    if not isinstance(raw_history, list):
        return JsonResponse({"error": "That request looked broken. Please try again."}, status=400)

    for item in raw_history:
        if (
            isinstance(item, dict)
            and item.get("role") in ("user", "assistant")
            and isinstance(item.get("text"), str)
            and item["text"].strip()
        ):
            history.append({"role": item["role"], "text": item["text"].strip()})

    history = history[-settings.MAX_HISTORY_MESSAGES:]
    # Gemini expects the conversation to start with a user turn.
    while history and history[0]["role"] != "user":
        history.pop(0)
    # Drop oldest messages until we're under the total size limit.
    while history and sum(len(h["text"]) for h in history) > settings.MAX_HISTORY_CHARS:
        history.pop(0)
        while history and history[0]["role"] != "user":
            history.pop(0)

    try:
        reply = ask_gemini(settings.GEMINI_API_KEY, settings.GEMINI_MODEL, history, message)
    except GeminiError as err:
        return JsonResponse({"error": err.message}, status=err.status)

    return JsonResponse({"reply": reply})
