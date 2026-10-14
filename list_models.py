"""Lists the Gemini models your API key can use.
Run from the boben_ai folder:  python list_models.py
Your key is read from .env and is never printed."""
import os
import requests
from dotenv import load_dotenv

load_dotenv(".env")
key = os.getenv("GEMINI_API_KEY", "").strip()
if not key:
    raise SystemExit("No GEMINI_API_KEY found in .env")

r = requests.get(
    "https://generativelanguage.googleapis.com/v1beta/models",
    headers={"x-goog-api-key": key},
    params={"pageSize": 200},
    timeout=30,
)
print("HTTP status:", r.status_code)
if r.status_code != 200:
    print(r.text[:500].replace(key, "<hidden>"))
    raise SystemExit(1)

names = [
    m["name"].replace("models/", "")
    for m in r.json().get("models", [])
    if "generateContent" in m.get("supportedGenerationMethods", [])
]
print("\nModels you can put in GEMINI_MODEL (those with 'flash' first):")
for n in sorted(names, key=lambda n: ("flash" not in n, n)):
    print("  ", n)
