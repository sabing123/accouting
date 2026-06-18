from rest_framework.routers import DefaultRouter
from django.urls import path, include

from receivables.api import views as receivables_views

router = DefaultRouter()
router.register(r'customers', receivables_views.CustomerViewSet, basename='customer')
router.register(r'invoices', receivables_views.InvoiceViewSet, basename='invoice')
router.register(r'receipts', receivables_views.ReceiptViewSet, basename='receipt')

urlpatterns = [
    path('', include(router.urls)),
]
