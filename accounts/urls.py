from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("signup/", views.signup, name="signup"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("profile/password/", views.password_view, name="password"),
    path("avatar/", views.avatar_view, name="avatar"),
    path("oauth/<str:provider>/start/", views.oauth_start, name="oauth_start"),
    path("oauth/<str:provider>/callback/", views.oauth_callback, name="oauth_callback"),
]
