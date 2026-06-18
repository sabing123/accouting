from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from django.urls import path, include

from ledger.api import views as ledger_views

router = DefaultRouter()
router.register(r'accounts', ledger_views.AccountViewSet, basename='account')
router.register(r'entries', ledger_views.JournalEntryViewSet, basename='journal-entry')

urlpatterns = [
    path('', include(router.urls)),
]
