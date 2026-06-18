from django.urls import path
from dashboard import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='index'),

    # HTMX endpoints
    path('htmx/stats/', views.DashboardStatsHTMXView.as_view(), name='stats-htmx'),
    path('htmx/cash-flow/', views.CashFlowChartHTMXView.as_view(), name='cash-flow-htmx'),
    path('htmx/revenue-expenses/', views.RevenueExpensesChartHTMXView.as_view(), name='revenue-expenses-htmx'),
    path('htmx/recent/', views.RecentActivityHTMXView.as_view(), name='recent-htmx'),
]
