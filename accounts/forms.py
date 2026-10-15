from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import COMMUNICATION_STYLES, TRAIT_CHOICES
from .text import clean_block, clean_line, parse_interests

User = get_user_model()


class SignUpForm(forms.Form):
    display_name = forms.CharField(max_length=60, required=False)
    email = forms.EmailField(max_length=254, error_messages={
        "required": "Enter your email address.", "invalid": "That email address doesn't look right."})
    password1 = forms.CharField(strip=False, error_messages={"required": "Choose a password."})
    password2 = forms.CharField(strip=False, error_messages={"required": "Type the password again to confirm it."})

    def clean_display_name(self):
        return clean_line(self.cleaned_data.get("display_name"), 60)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists. Try signing in instead.")
        return email

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords don't match.")
        elif p1 and "email" in data:
            try:
                validate_password(p1, User(email=data["email"], username=data["email"].split("@")[0]))
            except ValidationError as err:
                self.add_error("password1", err)
        return data


class LoginForm(forms.Form):
    email = forms.CharField(max_length=254, error_messages={"required": "Enter your email address."})
    password = forms.CharField(strip=False, error_messages={"required": "Enter your password."})
    remember = forms.BooleanField(required=False)


class ProfileForm(forms.Form):
    display_name = forms.CharField(max_length=60, required=False)
    bio = forms.CharField(max_length=500, required=False)
    interests = forms.CharField(max_length=600, required=False)
    traits = forms.MultipleChoiceField(choices=TRAIT_CHOICES, required=False)
    communication_style = forms.ChoiceField(choices=COMMUNICATION_STYLES, required=False)
    preferences = forms.CharField(max_length=500, required=False)
    avatar = forms.FileField(required=False)
    remove_avatar = forms.BooleanField(required=False)

    personalize = forms.BooleanField(required=False)
    use_name = forms.BooleanField(required=False)
    use_bio = forms.BooleanField(required=False)
    use_interests = forms.BooleanField(required=False)
    use_traits = forms.BooleanField(required=False)
    use_style = forms.BooleanField(required=False)
    use_preferences = forms.BooleanField(required=False)

    def clean_display_name(self):
        return clean_line(self.cleaned_data.get("display_name"), 60)

    def clean_bio(self):
        return clean_block(self.cleaned_data.get("bio"), 500)

    def clean_preferences(self):
        return clean_block(self.cleaned_data.get("preferences"), 500)

    def clean_interests(self):
        return parse_interests(self.cleaned_data.get("interests"))


class PasswordForm(forms.Form):
    current_password = forms.CharField(strip=False, required=False)
    new_password1 = forms.CharField(strip=False, error_messages={"required": "Choose a new password."})
    new_password2 = forms.CharField(strip=False, error_messages={"required": "Type the new password again."})

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_current_password(self):
        value = self.cleaned_data.get("current_password", "")
        if self.user.has_usable_password() and not self.user.check_password(value):
            raise ValidationError("Your current password isn't right.")
        return value

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("new_password1"), data.get("new_password2")
        if p1 and p2 and p1 != p2:
            self.add_error("new_password2", "The two passwords don't match.")
        elif p1:
            try:
                validate_password(p1, self.user)
            except ValidationError as err:
                self.add_error("new_password1", err)
        return data
