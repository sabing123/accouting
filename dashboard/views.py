from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView, View
from django.http import JsonResponse
from django.shortcuts import render

from organisations.middleware import TenantContextMixin
from dashboard.services import DashboardService


class DashboardView(LoginRequiredMixin, TenantContextMixin, TemplateView):
    template_name = 'dashboard/index.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        if not self.request.tenant:
            return context

        # Get overview stats
        context['overview'] = DashboardService.get_overview(self.request.tenant)

        # Get charts data
        context['cash_flow_trend'] = DashboardService.get_cash_flow_trend(self.request.tenant)
        context['revenue_vs_expenses'] = DashboardService.get_revenue_vs_expenses(self.request.tenant)
        context['ar_aging'] = DashboardService.get_ar_aging_summary(self.request.tenant)

        # Get lists
        context['recent_transactions'] = DashboardService.get_recent_transactions(self.request.tenant)
        context['top_customers'] = DashboardService.get_top_customers(self.request.tenant)
        context['top_vendors'] = DashboardService.get_top_vendors(self.request.tenant)
        context['ap_due_soon'] = DashboardService.get_ap_due_soon(self.request.tenant)

        return context


class DashboardStatsHTMXView(LoginRequiredMixin, TenantContextMixin, View):
    def get(self, request):
        if not request.tenant:
            return JsonResponse({})

        stats = DashboardService.get_overview(request.tenant)
        return render(request, 'dashboard/partials/stats.html', {'overview': stats})


class CashFlowChartHTMXView(LoginRequiredMixin, TenantContextMixin, View):
    def get(self, request):
        if not request.tenant:
            return JsonResponse({})

        months = int(request.GET.get('months', 6))
        data = DashboardService.get_cash_flow_trend(request.tenant, months)
        return JsonResponse({'data': data})


class RevenueExpensesChartHTMXView(LoginRequiredMixin, TenantContextMixin, View):
    def get(self, request):
        if not request.tenant:
            return JsonResponse({})

        months = int(request.GET.get('months', 6))
        data = DashboardService.get_revenue_vs_expenses(request.tenant, months)
        return JsonResponse({'data': data})


class RecentActivityHTMXView(LoginRequiredMixin, TenantContextMixin, View):
    def get(self, request):
        if not request.tenant:
            return render(request, 'dashboard/partials/recent.html', {'transactions': []})

        limit = int(request.GET.get('limit', 10))
        transactions = DashboardService.get_recent_transactions(request.tenant, limit)
        return render(request, 'dashboard/partials/recent.html', {'transactions': transactions})
