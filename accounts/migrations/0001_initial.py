import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="Profile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("display_name", models.CharField(blank=True, max_length=60)),
                ("bio", models.TextField(blank=True, max_length=500)),
                ("interests", models.JSONField(blank=True, default=list)),
                ("traits", models.JSONField(blank=True, default=list)),
                ("communication_style", models.CharField(
                    blank=True, max_length=20,
                    choices=[
                        ("", "No preference"), ("friendly", "Friendly and casual"),
                        ("direct", "Direct and to the point"), ("formal", "Formal and professional"),
                        ("encouraging", "Warm and encouraging"), ("detailed", "Thorough and detailed"),
                        ("playful", "Playful, with some humor"),
                    ])),
                ("preferences", models.TextField(blank=True, max_length=500)),
                ("avatar_data", models.BinaryField(blank=True, editable=False, null=True)),
                ("avatar_type", models.CharField(blank=True, max_length=30)),
                ("avatar_version", models.PositiveIntegerField(default=0)),
                ("avatar_url", models.URLField(blank=True, max_length=500)),
                ("personalize", models.BooleanField(default=True)),
                ("use_name", models.BooleanField(default=True)),
                ("use_bio", models.BooleanField(default=True)),
                ("use_interests", models.BooleanField(default=True)),
                ("use_traits", models.BooleanField(default=True)),
                ("use_style", models.BooleanField(default=True)),
                ("use_preferences", models.BooleanField(default=True)),
                ("email_verified", models.BooleanField(default=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE, related_name="profile", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="SocialAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=20)),
                ("uid", models.CharField(max_length=191)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE, related_name="social_accounts", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="socialaccount",
            constraint=models.UniqueConstraint(fields=("provider", "uid"), name="unique_provider_uid"),
        ),
    ]
