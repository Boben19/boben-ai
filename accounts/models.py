from django.conf import settings
from django.db import models

COMMUNICATION_STYLES = [
    ("", "No preference"),
    ("friendly", "Friendly and casual"),
    ("direct", "Direct and to the point"),
    ("formal", "Formal and professional"),
    ("encouraging", "Warm and encouraging"),
    ("detailed", "Thorough and detailed"),
    ("playful", "Playful, with some humor"),
]

TRAIT_CHOICES = [
    ("curious", "Curious"),
    ("analytical", "Analytical"),
    ("creative", "Creative"),
    ("organized", "Organized"),
    ("easygoing", "Easygoing"),
    ("ambitious", "Ambitious"),
    ("introverted", "Introverted"),
    ("extroverted", "Extroverted"),
    ("visual", "Visual learner"),
    ("hands-on", "Hands-on learner"),
]


class Profile(models.Model):
    """Extra details about a user. Created automatically with the account."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(max_length=60, blank=True)
    bio = models.TextField(max_length=500, blank=True)
    interests = models.JSONField(default=list, blank=True)          # list of short strings
    traits = models.JSONField(default=list, blank=True)             # list of keys from TRAIT_CHOICES
    communication_style = models.CharField(max_length=20, blank=True, choices=COMMUNICATION_STYLES)
    preferences = models.TextField(max_length=500, blank=True)      # free text, e.g. "use analogies"

    # Profile picture: stored as a small resized image in the database, so no media folder is needed.
    avatar_data = models.BinaryField(null=True, blank=True, editable=False)
    avatar_type = models.CharField(max_length=30, blank=True)
    avatar_version = models.PositiveIntegerField(default=0)
    avatar_url = models.URLField(max_length=500, blank=True)        # picture from Google/GitHub/Facebook (display only)

    # What the AI is allowed to use. Everything defaults to on, the master switch turns it all off.
    personalize = models.BooleanField(default=True)
    use_name = models.BooleanField(default=True)
    use_bio = models.BooleanField(default=True)
    use_interests = models.BooleanField(default=True)
    use_traits = models.BooleanField(default=True)
    use_style = models.BooleanField(default=True)
    use_preferences = models.BooleanField(default=True)

    # Local sign-ups are not email-verified (no mail server is configured), OAuth sign-ins are.
    email_verified = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profile of {self.user}"

    @property
    def has_avatar(self):
        return bool(self.avatar_data)

    @property
    def shown_name(self):
        return self.display_name or self.user.first_name or self.user.email.split("@")[0]


class SocialAccount(models.Model):
    """Links a user to an account at Google, GitHub or Facebook."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_accounts")
    provider = models.CharField(max_length=20)
    uid = models.CharField(max_length=191)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["provider", "uid"], name="unique_provider_uid")]

    def __str__(self):
        return f"{self.provider}:{self.uid}"
