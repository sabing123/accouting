"""Root URL configuration for multi-tenant setup."""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

# API Router
router = DefaultRouter()

urlpatterns = [
    path("api/v1/", include((router.urls, "api"), namespace="api-v1")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    path("account/", include("allauth.urls")),
    path("", include("dashboard.urls")),
    path("billing/", include("billing.urls")),
]

# Tenant-specific URL patterns (loaded when in tenant context)
tenant_urlpatterns = [
    path("", include("ledger.urls")),
    path("", include("payables.urls")),
    path("", include("receivables.urls")),
    path("", include("banking.urls")),
    path("", include("reports.urls")),
    path("", include("users.urls")),
    path("api/v1/", include("ledger.api_urls")),
    path("api/v1/", include("payables.api_urls")),
    path("api/v1/", include("receivables.api_urls")),
    path("api/v1/", include("banking.api_urls")),
    path("api/v1/", include("reports.api_urls")),
    path("api/v1/", include("billing.api_urls")),
    path("api/v1/", include("users.api_urls")),
]
