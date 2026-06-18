from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.views.generic import ListView, CreateView, DetailView, UpdateView, DeleteView, View
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy, reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib import messages
from django.db import transaction
from django.db.models import Q, Sum
from django.core.paginator import Paginator

from organisations.middleware import TenantContextMixin
from ledger.models import (
    Account, AccountType, AccountCategory, JournalEntry, JournalEntryLine,
    FiscalYear, FiscalPeriod, RecurringJournalEntry
)
from ledger.forms import AccountForm, JournalEntryForm, QuickJournalEntryForm, JournalEntryLineForm
from ledger.services import ChartOfAccountsService, JournalEntryService


class AccountListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = Account
    context_object_name = 'accounts'
    template_name = 'ledger/account_list.html'

    def get_queryset(self):
        queryset = Account.objects.filter(
            organisation=self.request.tenant
        ).select_related('account_type', 'category', 'parent')
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['account_types'] = AccountType.objects.filter(organisation=self.request.tenant)
        return context


class AccountCreateView(LoginRequiredMixin, TenantContextMixin, SuccessMessageMixin, CreateView):
    model = Account
    form_class = AccountForm
    template_name = 'ledger/account_form.html'
    success_message = _("Account '%(name)s' created successfully!")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organisation'] = self.request.tenant
        return kwargs

    def get_success_url(self):
        return reverse('ledger:account-list')


class AccountDetailView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = Account
    context_object_name = 'account'
    template_name = 'ledger/account_detail.html'

    def get_queryset(self):
        return Account.objects.filter(organisation=self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['recent_transactions'] = JournalEntryLine.objects.filter(
            account=self.object,
            entry__status=JournalEntry.Status.POSTED
        ).select_related('entry').order_by('-entry__date')[:10]
        return context


class AccountUpdateView(LoginRequiredMixin, TenantContextMixin, SuccessMessageMixin, UpdateView):
    model = Account
    form_class = AccountForm
    template_name = 'ledger/account_form.html'
    success_message = _("Account updated successfully!")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organisation'] = self.request.tenant
        return kwargs

    def get_queryset(self):
        return Account.objects.filter(organisation=self.request.tenant)

    def get_success_url(self):
        return reverse('ledger:account-detail', kwargs={'pk': self.object.pk})


class AccountDeactivateView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        account = get_object_or_404(Account, pk=pk, organisation=request.tenant)
        ChartOfAccountsService.deactivate_account(account)
        messages.success(request, _("Account deactivated successfully."))
        return redirect('ledger:account-list')


class AccountActivityView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = Account
    template_name = 'ledger/account_activity.html'
    context_object_name = 'account'

    def get_queryset(self):
        return Account.objects.filter(organisation=self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        start_date = self.request.GET.get('start_date')
        end_date = self.request.GET.get('end_date', str(timezone.now().date()))

        if not start_date:
            start_date = str(timezone.now().date().replace(day=1))

        from ledger.services import AccountBalanceService
        context['activity'] = AccountBalanceService.get_account_activity(
            account=self.object,
            start_date=start_date,
            end_date=end_date
        )
        context['start_date'] = start_date
        context['end_date'] = end_date
        return context


class JournalEntryListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = JournalEntry
    context_object_name = 'entries'
    template_name = 'ledger/entry_list.html'
    paginate_by = 25

    def get_queryset(self):
        queryset = JournalEntry.objects.filter(
            organisation=self.request.tenant
        ).select_related('created_by', 'posted_by').prefetch_related('lines__account')

        # Filters
        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        entry_type = self.request.GET.get('entry_type')
        if entry_type:
            queryset = queryset.filter(entry_type=entry_type)

        account = self.request.GET.get('account')
        if account:
            queryset = queryset.filter(lines__account_id=account).distinct()

        date_from = self.request.GET.get('date_from')
        if date_from:
            queryset = queryset.filter(date__gte=date_from)

        date_to = self.request.GET.get('date_to')
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        search = self.request.GET.get('q')
        if search:
            queryset = queryset.filter(
                Q(entry_number__icontains=search) |
                Q(description__icontains=search) |
                Q(reference__icontains=search)
            )

        return queryset.order_by('-date', '-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = JournalEntry.Status.choices
        context['type_choices'] = JournalEntry.EntryType.choices
        return context


class JournalEntryCreateView(LoginRequiredMixin, TenantContextMixin, SuccessMessageMixin, CreateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = 'ledger/entry_form.html'
    success_message = _("Journal entry created successfully!")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organisation'] = self.request.tenant
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['accounts'] = Account.objects.filter(
            organisation=self.request.tenant,
            is_active=True,
            allow_transactions=True
        ).order_by('code')
        return context

    def form_valid(self, form):
        lines_data = self.request.POST.getlist('lines')
        if not lines_data:
            messages.error(self.request, _("At least one line is required."))
            return self.form_invalid(form)

        try:
            lines = []
            for line_json in lines_data:
                import json
                line = json.loads(line_json)
                lines.append(line)

            entry = JournalEntryService.create_entry(
                organisation=self.request.tenant,
                date=form.cleaned_data['date'],
                description=form.cleaned_data['description'],
                lines=lines,
                created_by=self.request.user,
                reference=form.cleaned_data.get('reference', ''),
                entry_type=form.cleaned_data.get('entry_type', JournalEntry.EntryType.GENERAL),
            )

            self.object = entry
            return redirect(self.get_success_url())

        except Exception as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)

    def get_success_url(self):
        return reverse('ledger:entry-detail', kwargs={'pk': self.object.pk})


class JournalEntryDetailView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = JournalEntry
    context_object_name = 'entry'
    template_name = 'ledger/entry_detail.html'

    def get_queryset(self):
        return JournalEntry.objects.filter(organisation=self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['lines'] = self.object.lines.select_related('account', 'department').all()
        return context


class JournalEntryEditView(LoginRequiredMixin, TenantContextMixin, SuccessMessageMixin, UpdateView):
    model = JournalEntry
    form_class = JournalEntryForm
    template_name = 'ledger/entry_form.html'
    success_message = _("Journal entry updated successfully!")

    def get_queryset(self):
        return JournalEntry.objects.filter(
            organisation=self.request.tenant,
            status=JournalEntry.Status.DRAFT
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organisation'] = self.request.tenant
        return kwargs

    def get_success_url(self):
        return reverse('ledger:entry-detail', kwargs={'pk': self.object.pk})


class JournalEntryPostView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        entry = get_object_or_404(
            JournalEntry,
            pk=pk,
            organisation=request.tenant,
            status__in=[JournalEntry.Status.DRAFT, JournalEntry.Status.PENDING]
        )

        try:
            JournalEntryService.post_entry(entry, request.user)
            messages.success(request, _("Journal entry posted successfully."))
        except Exception as e:
            messages.error(request, str(e))

        return redirect('ledger:entry-detail', pk=pk)


class JournalEntryVoidView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        entry = get_object_or_404(
            JournalEntry,
            pk=pk,
            organisation=request.tenant,
            status=JournalEntry.Status.POSTED
        )

        reason = request.POST.get('reason', '')
        try:
            JournalEntryService.void_entry(entry, request.user, reason)
            messages.success(request, _("Journal entry voided successfully."))
        except Exception as e:
            messages.error(request, str(e))

        return redirect('ledger:entry-detail', pk=pk)


class QuickJournalEntryView(LoginRequiredMixin, TenantContextMixin, CreateView):
    form_class = QuickJournalEntryForm
    template_name = 'ledger/entry_quick.html'
    success_url = reverse_lazy('ledger:entry-list')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['organisation'] = self.request.tenant
        return kwargs

    def form_valid(self, form):
        try:
            entry = JournalEntryService.create_entry(
                organisation=self.request.tenant,
                date=form.cleaned_data['date'],
                description=form.cleaned_data['description'],
                lines=[
                    {'account': form.cleaned_data['debit_account'].pk, 'debit': form.cleaned_data['debit_amount'], 'credit': 0},
                    {'account': form.cleaned_data['credit_account'].pk, 'debit': 0, 'credit': form.cleaned_data['credit_amount']},
                ],
                created_by=self.request.user,
            )

            # Post immediately if requested
            if self.request.POST.get('post_immediately'):
                JournalEntryService.post_entry(entry, self.request.user)

            messages.success(self.request, _("Journal entry created successfully."))
            return redirect('ledger:entry-detail', pk=entry.pk)

        except Exception as e:
            messages.error(self.request, str(e))
            return self.form_invalid(form)


# Fiscal Year Management
class FiscalYearListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = FiscalYear
    context_object_name = 'fiscal_years'
    template_name = 'ledger/fiscal_year_list.html'

    def get_queryset(self):
        return FiscalYear.objects.filter(organisation=self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['periods'] = FiscalPeriod.objects.filter(
            organisation=self.request.tenant
        ).select_related('fiscal_year').order_by('-start_date')
        return context


class FiscalYearCreateView(LoginRequiredMixin, TenantContextMixin, SuccessMessageMixin, CreateView):
    model = FiscalYear
    fields = ['name', 'start_date', 'end_date']
    template_name = 'ledger/fiscal_year_form.html'
    success_message = _("Fiscal year '%(name)s' created successfully.")

    def form_valid(self, form):
        with transaction.atomic():
            form.instance.organisation = self.request.tenant
            response = super().form_valid(form)

            # Create periods
            JournalEntryService._create_periods(self.object, self.request.tenant)

        return response

    def get_success_url(self):
        return reverse('ledger:fiscal-year-list')


class FiscalYearCloseView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        fiscal_year = get_object_or_404(
            FiscalYear,
            pk=pk,
            organisation=request.tenant
        )

        fiscal_year.close(request.user)
        messages.success(request, _("Fiscal year closed successfully."))
        return redirect('ledger:fiscal-year-list')


class FiscalPeriodCloseView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        period = get_object_or_404(
            FiscalPeriod,
            pk=pk,
            organisation=request.tenant
        )

        period.status = FiscalPeriod.Status.CLOSED
        period.save()
        messages.success(request, _("Period closed successfully."))
        return redirect('ledger:fiscal-year-list')


class FiscalPeriodReopenView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        period = get_object_or_404(
            FiscalPeriod,
            pk=pk,
            organisation=request.tenant
        )

        period.status = FiscalPeriod.Status.OPEN
        period.save()
        messages.success(request, _("Period reopened successfully."))
        return redirect('ledger:fiscal-year-list')


# Recurring Entries
class RecurringEntryListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = RecurringJournalEntry
    context_object_name = 'recurring_entries'
    template_name = 'ledger/recurring_list.html'

    def get_queryset(self):
        return RecurringJournalEntry.objects.filter(organisation=self.request.tenant)


class RecurringEntryCreateView(LoginRequiredMixin, TenantContextMixin, SuccessMessageMixin, CreateView):
    model = RecurringJournalEntry
    fields = ['name', 'description', 'frequency', 'day_of_month', 'start_date', 'end_date']
    template_name = 'ledger/recurring_form.html'
    success_message = _("Recurring entry created successfully.")

    def form_valid(self, form):
        form.instance.organisation = self.request.tenant
        form.instance.created_by = self.request.user
        form.instance.template_lines = self.request.POST.getlist('template_lines')
        return super().form_valid(form)

    def get_success_url(self):
        return reverse('ledger:recurring-list')


class RecurringEntryUpdateView(LoginRequiredMixin, TenantContextMixin, SuccessMessageMixin, UpdateView):
    model = RecurringJournalEntry
    fields = ['name', 'description', 'frequency', 'day_of_month', 'start_date', 'end_date', 'is_active']
    template_name = 'ledger/recurring_form.html'
    success_message = _("Recurring entry updated successfully.")

    def get_queryset(self):
        return RecurringJournalEntry.objects.filter(organisation=self.request.tenant)

    def get_success_url(self):
        return reverse('ledger:recurring-list')


class RecurringEntryToggleView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        entry = get_object_or_404(
            RecurringJournalEntry,
            pk=pk,
            organisation=request.tenant
        )

        entry.is_active = not entry.is_active
        entry.save()

        status = _("activated") if entry.is_active else _("deactivated")
        messages.success(request, _("Recurring entry %(status)s.") % {'status': status})
        return redirect('ledger:recurring-list')


# HTMX Views
class AccountTreeView(LoginRequiredMixin, TenantContextMixin, View):
    def get(self, request, pk):
        account = get_object_or_404(Account, pk=pk, organisation=request.tenant)
        children = account.children.select_related('account_type', 'category').all()
        return render(request, 'ledger/partials/account_tree.html', {
            'account': account,
            'children': children,
        })


class JournalEntryLinesView(LoginRequiredMixin, TenantContextMixin, View):
    def get(self, request, pk):
        entry = get_object_or_404(JournalEntry, pk=pk, organisation=request.tenant)
        lines = entry.lines.select_related('account', 'department').all()
        return render(request, 'ledger/partials/entry_lines.html', {
            'entry': entry,
            'lines': lines,
        })
