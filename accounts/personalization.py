"""Turns a saved profile into a short note for the AI, using only what the user allowed."""
from .models import TRAIT_CHOICES
from .text import clean_line

TRAIT_LABELS = dict(TRAIT_CHOICES)

STYLE_NOTES = {
    "friendly": "Prefers a friendly, casual tone.",
    "direct": "Prefers direct answers: lead with the answer, skip the small talk.",
    "formal": "Prefers a formal, professional tone.",
    "encouraging": "Responds well to a warm, encouraging tone.",
    "detailed": "Prefers thorough explanations with reasoning and examples.",
    "playful": "Enjoys a playful tone with light humor.",
}


def first_name_for_ai(profile):
    """The name Boben may use, or '' if the user turned that off."""
    if not (profile.personalize and profile.use_name):
        return ""
    name = clean_line(profile.display_name, 60).split(" ")[0] if profile.display_name else ""
    return name


def build_profile_context(profile):
    """Bullet lines describing the person. Returns '' when personalization is off or nothing is shared."""
    if profile is None or not profile.personalize:
        return ""
    lines = []
    if profile.use_bio and profile.bio.strip():
        lines.append("About them: " + clean_line(profile.bio, 500))
    if profile.use_interests and profile.interests:
        items = [clean_line(i, 30) for i in profile.interests[:12]]
        lines.append("Interests: " + ", ".join(i for i in items if i))
    if profile.use_traits and profile.traits:
        labels = [TRAIT_LABELS[t] for t in profile.traits if t in TRAIT_LABELS]
        if labels:
            lines.append("Personality and learning traits: " + ", ".join(labels).lower())
    if profile.use_style and profile.communication_style in STYLE_NOTES:
        lines.append("Communication style: " + STYLE_NOTES[profile.communication_style])
    if profile.use_preferences and profile.preferences.strip():
        lines.append("Their stated preferences: " + clean_line(profile.preferences, 500))
    return "\n".join("- " + line for line in lines)
