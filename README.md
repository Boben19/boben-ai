# Boben AI 🍀: a personalized AI assistant PWA

Django + Bootstrap + vanilla JavaScript + Google Gemini. No database, no login.
The Gemini API key stays on the server (in `.env`) and never reaches the browser.

## Folder structure

```
boben_ai/
├── manage.py
├── requirements.txt
├── list_models.py          <- lists the Gemini models your key can use
├── .env.example            <- copy to .env and add your key
├── .gitignore              <- keeps .env out of GitHub
├── config/                 <- Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
└── assistant/              <- the app
    ├── gemini.py           <- Gemini API call + personality (system instruction)
    ├── views.py            <- page, /api/chat/, serviceworker.js
    ├── urls.py             <- routes
    ├── tests.py            <- tests (Gemini is faked)
    ├── templates/assistant/
    │   ├── index.html      <- chat page
    │   ├── offline.html    <- fallback page
    │   └── manifest.json   <- web app manifest (a template, so it can use {% static %})
    └── static/assistant/
        ├── css/style.css
        ├── js/app.js            <- chat UI, offline banner, install button
        ├── js/serviceworker.js  <- caching (served from "/" by views.service_worker)
        └── icons/               <- PWA icons
```

## Windows setup (PowerShell or Command Prompt)

1. Install Python 3.10+ from python.org. Tick **"Add Python to PATH"**.
2. Open a terminal in the `boben_ai` folder and run:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

PowerShell may block the activate script. If it does, run this once, then activate again:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

3. Get a free key at https://aistudio.google.com/apikey. Open `.env` in Notepad and set:

```
GEMINI_API_KEY=paste-your-key-here
GEMINI_MODEL=gemini-2.5-flash
```

`GEMINI_MODEL` can also be `gemini-3.5-flash-lite` or `gemini-3.8-flash`, whichever your free-tier key supports.
Also set `DJANGO_SECRET_KEY` to any long random text.

4. Start the server:

```powershell
python manage.py runserver
```

Open http://127.0.0.1:8000. **No migrations are needed**, since the project has no database.
To run the tests (they don't use your API key): `python manage.py test`.

## Test the PWA (use Chrome or Edge)

`localhost` and `127.0.0.1` count as secure, so service workers work without HTTPS.

**Installation**
1. Open http://127.0.0.1:8000 and wait a few seconds.
2. An **Install** button appears in the top bar (or in the menu on phones), and Chrome shows an install icon in the address bar. Click it.
3. Check the setup: DevTools (F12) → **Application** → **Manifest** (no errors, icons shown) and **Service Workers** (status "activated").

**Offline**
1. Load the page once while online, so the cache fills up.
2. In DevTools → **Application → Service Workers**, tick **Offline** (or turn off Wi-Fi).
3. Refresh. The interface should still load, the banner "You're offline…" appears, and the status pill turns orange.
4. Try sending a message. Boben explains that new answers need the internet. Untick **Offline** and everything works again.

Testing on a phone: the phone needs HTTPS to install the app (plain `http://192.168.x.x` won't work). Use a deployed HTTPS site or a tunnel.

## How it works (for your presentation)

- **Secure key:** `settings.py` loads `.env`. Only `gemini.py` reads the key, and it sends it in an HTTP header from the server. The browser only talks to `/api/chat/`.
- **Personality:** `SYSTEM_INSTRUCTION` in `gemini.py` is sent with every request, so Boben stays consistent.
- **Context:** the browser sends the last 12 messages. The server re-checks roles and size (`MAX_HISTORY_MESSAGES`, `MAX_HISTORY_CHARS`, `MAX_PROMPT_CHARS` in `settings.py`).
- **CSRF:** Django's middleware checks the `X-CSRFToken` header on every POST. The page sets the cookie with `@ensure_csrf_cookie`.
- **Safe output:** `app.js` escapes all HTML before adding simple formatting, so replies can't inject scripts.
- **Service worker location:** it is served from `/serviceworker.js` (not `/static/`) so it can control the whole site.
- **Cache rules:** pages use network-first, static files use cache-first, and `/api/` is never cached.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Boben AI isn't set up yet" | `.env` is missing or `GEMINI_API_KEY` is empty. Save it and restart the server. |
| "Gemini rejected the request" | The key is wrong, or the model isn't available to you. Try another `GEMINI_MODEL`. |
| "Gemini is busy… error 503" | That model is overloaded. Boben already tries backup models (`GEMINI_FALLBACK_MODELS`). Wait a minute, or put a different model first in `GEMINI_MODEL`. The server terminal shows Google's exact message. |
| "free-tier limit" (429) | Wait a minute. Free keys have per-minute and per-day limits. |
| "That Gemini model wasn't found" | Run `python list_models.py` to see which models your key can use, then put one in `GEMINI_MODEL` (no `models/` prefix) and restart. |
| `ModuleNotFoundError: django` | Activate the venv (`venv\Scripts\activate`), then `pip install -r requirements.txt`. |
| No Install button | The browser must support it (Chrome/Edge). Check DevTools → Application → Manifest for errors. If you already installed it, it hides. |
| Changed CSS/JS but the old one shows | Update `CACHE_VERSION` in `serviceworker.js`, or DevTools → Application → Service Workers → **Unregister**, then hard refresh (Ctrl+Shift+R). |
| Page looks unstyled offline | Open the page once online first, so Bootstrap (CDN) gets cached. |
| `DisallowedHost` error | Add the host to `DJANGO_ALLOWED_HOSTS` in `.env`. |

## Before deploying or sharing

- Never commit `.env`. If a key ever leaks, delete it in Google AI Studio and make a new one.
- In production set `DJANGO_DEBUG=False`, a real `DJANGO_SECRET_KEY`, and your domain in `DJANGO_ALLOWED_HOSTS`. Serve static files with `collectstatic` and a server such as WhiteNoise, and use HTTPS.
- Chat history is stored only in the user's own browser (localStorage). "Clear chat" removes it.
