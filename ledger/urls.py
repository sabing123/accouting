from django.urls import path
from ledger import views
from ledger.api import urls as api_urls

app_name = 'ledger'

urlpatterns = [
    # Chart of Accounts
    path('accounts/', views.AccountListView.as_view(), name='account-list'),
    path('accounts/create/', views.AccountCreateView.as_view(), name='account-create'),
    path('accounts/<uuid:pk>/', views.AccountDetailView.as_view(), name='account-detail'),
    path('accounts/<uuid:pk>/edit/', views.AccountUpdateView.as_view(), name='account-edit'),
    path('accounts/<uuid:pk>/deactivate/', views.AccountDeactivateView.as_view(), name='account-deactivate'),
    path('accounts/<uuid:pk>/activity/', views.AccountActivityView.as_view(), name='account-activity'),

    # Journal Entries
    path('entries/', views.JournalEntryListView.as_view(), name='entry-list'),
    path('entries/create/', views.JournalEntryCreateView.as_view(), name='entry-create'),
    path('entries/<uuid:pk>/', views.JournalEntryDetailView.as_view(), name='entry-detail'),
    path('entries/<uuid:pk>/edit/', views.JournalEntryEditView.as_view(), name='entry-edit'),
    path('entries/<uuid:pk>/post/', views.JournalEntryPostView.as_view(), name='entry-post'),
    path('entries/<uuid:pk>/void/', views.JournalEntryVoidView.as_view(), name='entry-void'),
    path('entries/quick/', views.QuickJournalEntryView.as_view(), name='entry-quick'),

    # Fiscal Year / Period Management
    path('fiscal-years/', views.FiscalYearListView.as_view(), name='fiscal-year-list'),
    path('fiscal-years/create/', views.FiscalYearCreateView.as_view(), name='fiscal-year-create'),
    path('fiscal-years/<uuid:pk>/close/', views.FiscalYearCloseView.as_view(), name='fiscal-year-close'),
    path('periods/<uuid:pk>/close/', views.FiscalPeriodCloseView.as_view(), name='period-close'),
    path('periods/<uuid:pk>/reopen/', views.FiscalPeriodReopenView.as_view(), name='period-reopen'),

    # Recurring Entries
    path('recurring/', views.RecurringEntryListView.as_view(), name='recurring-list'),
    path('recurring/create/', views.RecurringEntryCreateView.as_view(), name='recurring-create'),
    path('recurring/<uuid:pk>/edit/', views.RecurringEntryUpdateView.as_view(), name='recurring-edit'),
    path('recurring/<uuid:pk>/toggle/', views.RecurringEntryToggleView.as_view(), name='recurring-toggle'),

    # HTMX Endpoints
    path('htmx/accounts/<uuid:pk>/tree/', views.AccountTreeView.as_view(), name='account-tree'),
    path('htmx/entries/<uuid:pk>/lines/', views.JournalEntryLinesView.as_view(), name='entry-lines'),

    # Include API URLs
    path('api/', (api_urls, 'api'), namespace='api'),
]
