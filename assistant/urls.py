from django.urls import path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("offline/", views.offline, name="offline"),
    path("api/chat/", views.chat, name="chat"),
    # PWA files live at the site root so they can control the whole app.
    path("serviceworker.js", views.service_worker, name="serviceworker"),
    path(
        "manifest.json",
        TemplateView.as_view(template_name="assistant/manifest.json", content_type="application/manifest+json"),
        name="manifest",
    ),
]
