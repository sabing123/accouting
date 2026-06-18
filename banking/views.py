from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, DetailView, UpdateView, View
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.utils import timezone

from organisations.middleware import TenantContextMixin
from banking.models import BankAccount, BankTransaction, BankReconciliation, BankTransactionImport, Transfer
from banking.services import (
    BankAccountService, BankTransactionImportService,
    ReconciliationService, TransferService
)


class BankAccountListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = BankAccount
    context_object_name = 'bank_accounts'
    template_name = 'banking/account_list.html'

    def get_queryset(self):
        return BankAccount.objects.filter(organisation=self.request.tenant)


class BankAccountCreateView(LoginRequiredMixin, TenantContextMixin, CreateView):
    model = BankAccount
    template_name = 'banking/account_form.html'
    success_url = reverse_lazy('banking:account-list')
    fields = ['name', 'bank_name', 'account_number', 'routing_number', 'account_type', 'account', 'currency', 'opening_balance', 'notes']

    def form_valid(self, form):
        form.instance.organisation = self.request.tenant
        messages.success(self.request, _("Bank account created successfully."))
        return super().form_valid(form)


class BankAccountDetailView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = BankAccount
    context_object_name = 'bank_account'
    template_name = 'banking/account_detail.html'

    def get_queryset(self):
        return BankAccount.objects.filter(organisation=self.request.tenant)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['transactions'] = self.object.transactions.order_by('-transaction_date')[:50]
        context['imports'] = self.object.imports.order_by('-created_at')[:5]
        return context


class BankTransactionImportView(LoginRequiredMixin, TenantContextMixin, View):
    template_name = 'banking/import_form.html'

    def get(self, request):
        bank_accounts = BankAccount.objects.filter(organisation=request.tenant)
        return render(request, self.template_name, {'bank_accounts': bank_accounts})

    def post(self, request):
        bank_account_id = request.POST.get('bank_account')
        csv_file = request.FILES.get('csv_file')

        bank_account = get_object_or_404(BankAccount, pk=bank_account_id, organisation=request.tenant)

        try:
            import_record = BankTransactionImportService.import_from_csv(
                bank_account=bank_account,
                csv_file=csv_file,
                imported_by=request.user,
            )

            # Auto-match transactions
            BankTransactionImportService.auto_match_transactions(bank_account)

            messages.success(request, f"Imported {import_record.total_transactions} transactions successfully.")
            return redirect('banking:import-detail', pk=import_record.pk)
        except Exception as e:
            messages.error(request, str(e))
            return self.get(request)


class BankTransactionListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = BankTransaction
    context_object_name = 'transactions'
    template_name = 'banking/transaction_list.html'
    paginate_by = 50

    def get_queryset(self):
        queryset = BankTransaction.objects.filter(
            bank_account__organisation=self.request.tenant
        ).select_related('bank_account')

        bank_account = self.request.GET.get('account')
        if bank_account:
            queryset = queryset.filter(bank_account_id=bank_account)

        status = self.request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)

        return queryset.order_by('-transaction_date')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['bank_accounts'] = BankAccount.objects.filter(organisation=self.request.tenant)
        return context


class ReconciliationListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = BankReconciliation
    context_object_name = 'reconciliations'
    template_name = 'banking/reconciliation_list.html'

    def get_queryset(self):
        return BankReconciliation.objects.filter(
            bank_account__organisation=self.request.tenant
        ).select_related('bank_account')


class ReconciliationStartView(LoginRequiredMixin, TenantContextMixin, View):
    template_name = 'banking/reconciliation_form.html'

    def get(self, request):
        bank_accounts = BankAccount.objects.filter(organisation=request.tenant)
        return render(request, self.template_name, {'bank_accounts': bank_accounts})

    def post(self, request):
        bank_account_id = request.POST.get('bank_account')
        statement_date = request.POST.get('statement_date')
        statement_balance = request.POST.get('statement_balance')

        bank_account = get_object_or_404(BankAccount, pk=bank_account_id, organisation=request.tenant)

        try:
            reconciliation = ReconciliationService.start_reconciliation(
                bank_account=bank_account,
                statement_date=statement_date,
                statement_balance=statement_balance,
                reconciled_by=request.user,
            )

            # Calculate adjustments
            ReconciliationService.calculate_adjustments(reconciliation)

            return redirect('banking:reconciliation-detail', pk=reconciliation.pk)
        except Exception as e:
            messages.error(request, str(e))
            return self.get(request)


class ReconciliationDetailView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = BankReconciliation
    context_object_name = 'reconciliation'
    template_name = 'banking/reconciliation_detail.html'

    def get_queryset(self):
        return BankReconciliation.objects.filter(
            bank_account__organisation=self.request.tenant
        ).select_related('bank_account')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get unreconciled bank transactions
        context['unreconciled_transactions'] = BankTransaction.objects.filter(
            bank_account=self.object.bank_account,
            status__in=['unmatched', 'matched'],
            transaction_date__lte=self.object.statement_date,
        )

        # Get unreconciled journal lines
        context['unreconciled_lines'] = JournalEntryLine.objects.filter(
            account=self.object.bank_account.account,
            reconciled=False,
            entry__status='posted',
            entry__date__lte=self.object.statement_date,
        ).select_related('entry')

        return context


class ReconciliationLineView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        from ledger.models import JournalEntryLine

        reconciliation = get_object_or_404(
            BankReconciliation,
            pk=pk,
            bank_account__organisation=request.tenant
        )

        journal_line_id = request.POST.get('journal_line')
        bank_transaction_id = request.POST.get('bank_transaction')

        journal_line = get_object_or_404(JournalEntryLine, pk=journal_line_id)
        bank_transaction = None
        if bank_transaction_id:
            bank_transaction = get_object_or_404(BankTransaction, pk=bank_transaction_id)

        try:
            ReconciliationService.reconcile_line(
                reconciliation=reconciliation,
                journal_line=journal_line,
                bank_transaction=bank_transaction,
            )
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})


class ReconciliationCompleteView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        reconciliation = get_object_or_404(
            BankReconciliation,
            pk=pk,
            bank_account__organisation=request.tenant,
            status='in_progress'
        )

        try:
            ReconciliationService.complete_reconciliation(reconciliation, request.user)
            messages.success(request, _("Reconciliation completed successfully."))
        except Exception as e:
            messages.error(request, str(e))

        return redirect('banking:reconciliation-detail', pk=pk)


# Bank Transfers
class TransferListView(LoginRequiredMixin, TenantContextMixin, ListView):
    model = Transfer
    context_object_name = 'transfers'
    template_name = 'banking/transfer_list.html'

    def get_queryset(self):
        return Transfer.objects.filter(organisation=self.request.tenant)

class TransferCreateView(LoginRequiredMixin, TenantContextMixin, View):
    template_name = 'banking/transfer_form.html'

    def get(self, request):
        bank_accounts = BankAccount.objects.filter(organisation=request.tenant)
        return render(request, self.template_name, {'bank_accounts': bank_accounts})

    def post(self, request):
        from_account_id = request.POST.get('from_account')
        to_account_id = request.POST.get('to_account')
        amount = request.POST.get('amount')
        transfer_date = request.POST.get('transfer_date')
        memo = request.POST.get('memo', '')

        from_account = get_object_or_404(BankAccount, pk=from_account_id, organisation=request.tenant)
        to_account = get_object_or_404(BankAccount, pk=to_account_id, organisation=request.tenant)

        try:
            transfer = TransferService.create_transfer(
                organisation=request.tenant,
                transfer_date=transfer_date,
                amount=amount,
                from_account=from_account,
                to_account=to_account,
                created_by=request.user,
                memo=memo,
            )

            if request.POST.get('process_immediately'):
                TransferService.process_transfer(transfer, request.user)

            messages.success(request, _("Transfer created successfully."))
            return redirect('banking:transfer-detail', pk=transfer.pk)
        except Exception as e:
            messages.error(request, str(e))
            return self.get(request)


class TransferDetailView(LoginRequiredMixin, TenantContextMixin, DetailView):
    model = Transfer
    context_object_name = 'transfer'
    template_name = 'banking/transfer_detail.html'

    def get_queryset(self):
        return Transfer.objects.filter(organisation=self.request.tenant)


class TransferProcessView(LoginRequiredMixin, TenantContextMixin, View):
    def post(self, request, pk):
        transfer = get_object_or_404(Transfer, pk=pk, organisation=request.tenant)

        try:
            TransferService.process_transfer(transfer, request.user)
            messages.success(request, _("Transfer processed successfully."))
        except Exception as e:
            messages.error(request, str(e))

        return redirect('banking:transfer-detail', pk=pk)
