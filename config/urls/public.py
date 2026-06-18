"""Public URLs - accessible without tenant context."""

from django.urls import path, include
from django.views.generic import TemplateView

urlpatterns = [
    path("", TemplateView.as_view(template_name="public/home.html"), name="public-home"),
    path("pricing/", TemplateView.as_view(template_name="public/pricing.html"), name="public-pricing"),
    path("features/", TemplateView.as_view(template_name="public/features.html"), name="public-features"),
    path("account/", include("allauth.urls")),
    path("signup/", include("organisations.urls")),
]
