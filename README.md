# Boben: a personal study partner (PWA)

Developed by **Jhon Grover Longsud**.

Django + Bootstrap + vanilla JavaScript + Google Gemini, with accounts (email/password, Google, GitHub, Facebook) and a personal profile.
The Gemini key and all OAuth client secrets stay on the server (in `.env`) and never reach the browser.

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
├── accounts/               <- sign-up, sign-in, OAuth, profile, personalization
│   ├── models.py           <- Profile, SocialAccount
│   ├── views.py, forms.py  <- pages and validation
│   ├── oauth.py            <- Google / GitHub / Facebook code flow (server side)
│   ├── services.py         <- find/link/create the user for an OAuth login
│   ├── personalization.py  <- turns the saved profile into AI context (respects the switches)
│   ├── avatars.py          <- validates and resizes profile pictures
│   └── templates/accounts/ <- login, signup, profile pages
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

## Accounts, profile and personalization

- **Sign-in is required** to use the chat and `/api/chat/` (this also keeps strangers from spending your Gemini quota). Pages: `/accounts/login/`, `/accounts/signup/`, `/accounts/profile/`.
- **Email + password:** passwords are hashed by Django, validated (min. 8 characters, not common, not all digits), and wrong-password attempts are throttled (5 per 5 minutes per address + email). "Keep me signed in" lasts 14 days, otherwise the session ends when the browser closes. Signing out is a POST and also clears the offline copy of the chat page.
- **OAuth:** Google (with PKCE), GitHub and Facebook use the authorization-code flow with a one-time `state` check. Secrets are only used server-to-server.
- **Account linking:** if a provider-verified email matches an existing account, the two are linked. If that existing account never proved its email (a plain sign-up), its old password and other links are removed when the owner signs in through a provider, so nobody can pre-register your email and keep access. Facebook emails are never treated as verified, so Facebook never links into an existing account.
- **Profile:** name, picture (resized to 256 px and stored in the database), bio, interests, personality traits, communication style, free-text preferences. Set or change your password there too.
- **Personalization:** a master switch plus one switch per field decide what is added to the AI prompt on the server. The text is cleaned, framed as background information (not instructions), and is never sent to anyone but Gemini.
- **Chats** are still stored in the browser, now kept separately for each account on a device. Chats saved before accounts existed move to the first account that signs in.
- **Emojis** now drift softly inside the page background (under the text) and appear in headings and labels. Tap-to-pop and drag are gone because the emojis no longer sit on top. Star, heart and timer still play a short burst. Turn the background emojis off in Settings.

## What the redesign added

- **Look:** frosted-glass panels over a soft colour backdrop, iOS-style bubbles, rounded controls, safe-area support for iPhone notches, automatic light/dark mode.
- **Multiple chats:** a sidebar list, rename by tapping the title, delete with Undo, and a new chat shortcut (Ctrl/Cmd + K, or long-press the app icon once installed).
- **Modes:** Chat, Study, Code, Write, Plan. The mode is sent with each message and adds a short note to the personality (`MODE_NOTES` in `gemini.py`).
- **Settings sheet:** Auto/Light/Dark, reply length (Short/Balanced/Detailed), text size, and a link to your profile (your name now lives there).
- **Reply tools:** copy, read aloud, write a new reply, copy button on code blocks, dictation (where the browser supports it), and save a chat as a .txt file.
- **Background emojis:** soft emojis drift inside the page background, under the text, and appear in headings and labels. Turn them off in Settings. They stop moving if the device asks for reduced motion.
- **Saved answers:** tap the star on any reply to keep it. Open the list from the sidebar to read, copy or remove it later.
- **Follow-up chips:** after each reply, one tap sends things like "Quiz me on this" or "Explain simpler". The chips change with the mode.
- **Stop button:** the send button turns into a stop button while Boben is replying.
- **Search chats:** filters by title and by what was said inside the chat.
- **Focus timer:** Focus / Short break / Long break with a progress ring, a note on what you're working on, a count of today's sessions, and a sound plus emoji shower when time is up. It keeps running if you reload the page.
- **Text size and love button:** Small / Medium / Large text, and a heart on each reply that sends hearts floating up.
- **About:** tap "Developed by Jhon Grover Longsud" in the sidebar.
- **Offline:** the app still opens and old chats stay readable. An "Offline" pill and a banner appear, and the message stays in the box until you reconnect.
- **Safety:** mode, length and name are checked on the server against a fixed list before they reach the prompt. The API key still never leaves the server.
- **Voice of the app:** the interface and the personality never label themselves as "AI". If someone sincerely asks whether they are talking to a person or a program, Boben answers honestly.

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

4. Create the database (accounts and sessions) and start the server:

```powershell
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000. You will land on the sign-in page. Create an account, or use a provider once it is configured below.
To run the tests (they don't use your API key or any provider): `python manage.py test`.

## OAuth setup (what you must configure)

Put the secrets in `.env` (never in code or Git), then restart the server. A provider button only works when both its ID and secret are set. While `DJANGO_DEBUG=True`, unconfigured providers show greyed out. When it is `False` they are hidden.

The callback URL is `<your site>` + `/accounts/oauth/<provider>/callback/`. Use `http://127.0.0.1:8000` locally (register `http://localhost:8000` too if you open the site that way), and your real `https://` address in production.

| Provider | Where | What to set |
|---|---|---|
| Google | Google Cloud Console → APIs & Services → Credentials → your OAuth client (Web application) | Authorized redirect URIs: `http://127.0.0.1:8000/accounts/oauth/google/callback/`, `http://localhost:8000/accounts/oauth/google/callback/`, and the production one. In `.env`: `GOOGLE_CLIENT_SECRET`. Check the OAuth consent screen is configured, and add yourself as a test user while it is in Testing mode. |
| GitHub | GitHub → Settings → Developer settings → OAuth Apps | Authorization callback URL: `http://127.0.0.1:8000/accounts/oauth/github/callback/` (an OAuth App allows one, so make a second app for production). In `.env`: `GITHUB_CLIENT_SECRET`. |
| Facebook | developers.facebook.com → create an app (use case: Authenticate and request data from users with Facebook Login) | Facebook Login → Settings → Valid OAuth Redirect URIs: the Facebook callback URL. App settings → Basic: copy **App ID** and **App Secret** into `FACEBOOK_APP_ID` and `FACEBOOK_APP_SECRET`. Permissions used: `email`, `public_profile` (both available in Development mode). Switch the app to Live mode, with a privacy policy URL, before anyone other than the app's roles can sign in. |

Facebook calls use Graph API `v25.0` (`FACEBOOK_GRAPH_VERSION`). Facebook accounts without an email address can't sign up, because the app needs one.

## Test the PWA (use Chrome or Edge)

`localhost` and `127.0.0.1` count as secure, so service workers work without HTTPS.

**Installation**
1. Open http://127.0.0.1:8000 and wait a few seconds.
2. An **Install app** button appears at the bottom of the sidebar, and Chrome shows an install icon in the address bar. Click it. On an iPhone, the button shows how to use Share → Add to Home Screen.
3. Check the setup: DevTools (F12) → **Application** → **Manifest** (no errors, icons shown) and **Service Workers** (status "activated").

**Offline**
1. Load the page once while online, so the cache fills up.
2. In DevTools → **Application → Service Workers**, tick **Offline** (or turn off Wi-Fi).
3. Refresh. The interface should still load, the "Offline" pill and the banner appear at the top.
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
| "Boben isn't set up yet" | `.env` is missing or `GEMINI_API_KEY` is empty. Save it and restart the server. |
| "Gemini rejected the request" | The key is wrong, or the model isn't available to you. Try another `GEMINI_MODEL`. |
| "Gemini is busy… error 503" | That model is overloaded. Boben already tries backup models (`GEMINI_FALLBACK_MODELS`). Wait a minute, or put a different model first in `GEMINI_MODEL`. The server terminal shows Google's exact message. |
| "free-tier limit" (429) | Wait a minute. Free keys have per-minute and per-day limits. |
| "That Gemini model wasn't found" | Run `python list_models.py` to see which models your key can use, then put one in `GEMINI_MODEL` (no `models/` prefix) and restart. |
| `ModuleNotFoundError: django` | Activate the venv (`venv\Scripts\activate`), then `pip install -r requirements.txt`. |
| No Install button | The browser must support it (Chrome/Edge). Check DevTools → Application → Manifest for errors. If you already installed it, it hides. |
| Changed CSS/JS but the old one shows | Update `CACHE_VERSION` in `serviceworker.js`, or DevTools → Application → Service Workers → **Unregister**, then hard refresh (Ctrl+Shift+R). |
| Page looks unstyled offline | Open the page once online first, so Bootstrap (CDN) gets cached. |
| "redirect_uri_mismatch" (Google) or "redirect URI" error | The callback URL registered with the provider must match exactly, including `http`/`https`, `127.0.0.1` vs `localhost`, the port and the trailing slash. |
| Signed in, but bounced to the sign-in page right away | With `DJANGO_DEBUG=False`, cookies are `Secure` and need HTTPS. Use HTTPS, or keep `DJANGO_DEBUG=True` on your own computer. |
| OAuth works locally but fails online | Set `SITE_URL`, `DJANGO_BEHIND_PROXY=True` (if a proxy terminates HTTPS) and `DJANGO_CSRF_TRUSTED_ORIGINS`. |
| `no such table: auth_user` | Run `python manage.py migrate`. |
| `DisallowedHost` error | Add the host to `DJANGO_ALLOWED_HOSTS` in `.env`. |

## Before deploying or sharing

- Never commit `.env`. If a key ever leaks, delete it in Google AI Studio and make a new one.
- In production set `DJANGO_DEBUG=False`, a real `DJANGO_SECRET_KEY`, your domain in `DJANGO_ALLOWED_HOSTS`, `SITE_URL`, and `DJANGO_CSRF_TRUSTED_ORIGINS`. Serve static files with `collectstatic` and a server such as WhiteNoise, and use HTTPS.
- Put `DATABASE_PATH` on storage that survives restarts, and back it up. It holds accounts, profiles and pictures.
- If a client secret ever leaks, regenerate it in the provider's dashboard and update `.env`.
- There is no email sending yet, so there is no "forgot password" and no email verification for email sign-ups. Adding an email backend is the next step for both.
- Chat history is stored only in the user's own browser (localStorage), per account. "Delete all chats" in Settings removes it.
