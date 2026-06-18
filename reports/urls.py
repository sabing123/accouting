from django.urls import path
from reports import views

app_name = 'reports'

urlpatterns = [
    path('', views.FinancialReportsIndexView.as_view(), name='index'),

    # Financial Statements
    path('trial-balance/', views.TrialBalanceReportView.as_view(), name='trial-balance'),
    path('balance-sheet/', views.BalanceSheetReportView.as_view(), name='balance-sheet'),
    path('income-statement/', views.IncomeStatementReportView.as_view(), name='income-statement'),
    path('cash-flow/', views.CashFlowReportView.as_view(), name='cash-flow'),

    # Aging Reports
    path('aged-receivables/', views.AgedReceivablesReportView.as_view(), name='aged-receivables'),
    path('aged-payables/', views.AgedPayablesReportView.as_view(), name='aged-payables'),

    # Detailed Reports
    path('general-ledger/', views.GeneralLedgerReportView.as_view(), name='general-ledger'),

    # Export
    path('export/<str:report_type>/', views.ReportExportView.as_view(), name='export'),
]
