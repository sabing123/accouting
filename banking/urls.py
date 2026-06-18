from django.urls import path
from banking import views

app_name = 'banking'

urlpatterns = [
    # Bank Accounts
    path('accounts/', views.BankAccountListView.as_view(), name='account-list'),
    path('accounts/create/', views.BankAccountCreateView.as_view(), name='account-create'),
    path('accounts/<uuid:pk>/', views.BankAccountDetailView.as_view(), name='account-detail'),

    # Transactions
    path('transactions/', views.BankTransactionListView.as_view(), name='transaction-list'),
    path('transactions/import/', views.BankTransactionImportView.as_view(), name='transaction-import'),

    # Reconciliation
    path('reconciliation/', views.ReconciliationListView.as_view(), name='reconciliation-list'),
    path('reconciliation/start/', views.ReconciliationStartView.as_view(), name='reconciliation-start'),
    path('reconciliation/<uuid:pk>/', views.ReconciliationDetailView.as_view(), name='reconciliation-detail'),
    path('reconciliation/<uuid:pk>/line/', views.ReconciliationLineView.as_view(), name='reconciliation-line'),
    path('reconciliation/<uuid:pk>/complete/', views.ReconciliationCompleteView.as_view(), name='reconciliation-complete'),

    # Transfers
    path('transfers/', views.TransferListView.as_view(), name='transfer-list'),
    path('transfers/create/', views.TransferCreateView.as_view(), name='transfer-create'),
    path('transfers/<uuid:pk>/', views.TransferDetailView.as_view(), name='transfer-detail'),
    path('transfers/<uuid:pk>/process/', views.TransferProcessView.as_view(), name='transfer-process'),
]
