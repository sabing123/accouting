from rest_framework.routers import DefaultRouter
from django.urls import path, include

from payables.api import views as payables_views

router = DefaultRouter()
router.register(r'vendors', payables_views.VendorViewSet, basename='vendor')
router.register(r'bills', payables_views.BillViewSet, basename='bill')
router.register(r'payments', payables_views.PaymentViewSet, basename='payment')

urlpatterns = [
    path('', include(router.urls)),
]
