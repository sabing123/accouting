from django.utils import timezone
from django.db.models import Sum, Count, Q, Avg
from decimal import Decimal
from datetime import timedelta
from dateutil.relativedelta import relativedelta

from ledger.models import Account, JournalEntry, FiscalYear, FiscalPeriod
from receivables.models import Invoice, Customer, Receipt
from payables.models import Bill, Vendor, Payment
from banking.models import BankAccount
from organisations.models import Organisation


class DashboardService:
    """Service for dashboard statistics and metrics."""

    @staticmethod
    def get_overview(organisation: Organisation) -> dict:
        """Get overview statistics for the organisation."""
        today = timezone.now().date()
        month_start = today.replace(day=1)
        year_start = today.replace(month=organisation.fiscal_year_start_month, day=1)

        # Get cash balance
        cash_accounts = Account.objects.filter(
            organisation=organisation,
            is_bank_account=True
        )

        cash_balance = sum(account.current_balance for account in cash_accounts)

        # Accounts Receivable
        ar_balance = Invoice.objects.filter(
            organisation=organisation,
            status__in=['sent', 'partial']
        ).aggregate(total=Sum('balance'))['total'] or Decimal('0')

        # Accounts Payable
        ap_balance = Bill.objects.filter(
            organisation=organisation,
            status__in=['open', 'partial']
        ).aggregate(total=Sum('balance'))['total'] or Decimal('0')

        # Monthly metrics
        monthly_revenue = Invoice.objects.filter(
            organisation=organisation,
            invoice_date__gte=month_start,
            status__in=['sent', 'partial', 'paid']
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')

        monthly_expenses = Bill.objects.filter(
            organisation=organisation,
            bill_date__gte=month_start,
            status__in=['open', 'partial', 'paid']
        ).aggregate(total=Sum('total'))['total'] or Decimal('0')

        # Overdue counts
        overdue_receivables = Invoice.objects.filter(
            organisation=organisation,
            status__in=['sent', 'partial'],
            due_date__lt=today
        ).count()

        overdue_payables = Bill.objects.filter(
            organisation=organisation,
            status__in=['open', 'partial'],
            due_date__lt=today
        ).count()

        return {
            'cash_balance': cash_balance,
            'ar_balance': ar_balance,
            'ap_balance': ap_balance,
            'working_capital': cash_balance + ar_balance - ap_balance,
            'monthly_revenue': monthly_revenue,
            'monthly_expenses': monthly_expenses,
            'monthly_profit': monthly_revenue - monthly_expenses,
            'overdue_receivables': overdue_receivables,
            'overdue_payables': overdue_payables,
            'active_customers': Customer.objects.filter(organisation=organisation, is_active=True).count(),
            'active_vendors': Vendor.objects.filter(organisation=organisation, is_active=True).count(),
        }

    @staticmethod
    def get_cash_flow_trend(organisation: Organisation, months: int = 6) -> list:
        """Get cash flow trend for the last N months."""
        today = timezone.now().date()
        trend = []

        for i in range(months - 1, -1, -1):
            month_end = today - relativedelta(months=i)
            month_end = month_end.replace(day=1) + relativedelta(months=1) - timedelta(days=1)
            month_start = month_end.replace(day=1)

            # Inflows (receipts)
            inflows = Receipt.objects.filter(
                organisation=organisation,
                receipt_date__gte=month_start,
                receipt_date__lte=month_end
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            # Outflows (payments)
            outflows = Payment.objects.filter(
                organisation=organisation,
                payment_date__gte=month_start,
                payment_date__lte=month_end
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

            trend.append({
                'month': month_start.strftime('%b %Y'),
                'inflows': inflows,
                'outflows': outflows,
                'net': inflows - outflows,
            })

        return trend

    @staticmethod
    def get_revenue_vs_expenses(organisation: Organisation, months: int = 6) -> list:
        """Get revenue vs expenses comparison."""
        today = timezone.now().date()
        data = []

        for i in range(months - 1, -1, -1):
            month_end = today - relativedelta(months=i)
            month_end = month_end.replace(day=1) + relativedelta(months=1) - timedelta(days=1)
            month_start = month_end.replace(day=1)

            revenue = Invoice.objects.filter(
                organisation=organisation,
                invoice_date__gte=month_start,
                invoice_date__lte=month_end,
                status__in=['sent', 'partial', 'paid']
            ).aggregate(total=Sum('total'))['total'] or Decimal('0')

            expenses = Bill.objects.filter(
                organisation=organisation,
                bill_date__gte=month_start,
                bill_date__lte=month_end,
                status__in=['open', 'partial', 'paid']
            ).aggregate(total=Sum('total'))['total'] or Decimal('0')

            data.append({
                'month': month_start.strftime('%b'),
                'revenue': revenue,
                'expenses': expenses,
                'profit': revenue - expenses,
            })

        return data

    @staticmethod
    def get_top_customers(organisation: Organisation, limit: int = 5) -> list:
        """Get top customers by revenue."""
        return Customer.objects.filter(
            organisation=organisation
        ).annotate(
            total_revenue=Sum('invoices__total')
        ).filter(
            total_revenue__gt=0
        ).order_by('-total_revenue')[:limit]

    @staticmethod
    def get_top_vendors(organisation: Organisation, limit: int = 5) -> list:
        """Get top vendors by spend."""
        return Vendor.objects.filter(
            organisation=organisation
        ).annotate(
            total_spend=Sum('bills__total')
        ).filter(
            total_spend__gt=0
        ).order_by('-total_spend')[:limit]

    @staticmethod
    def get_recent_transactions(organisation: Organisation, limit: int = 10) -> list:
        """Get recent transactions across all types."""
        today = timezone.now().date()

        transactions = []

        # Recent invoices
        for invoice in Invoice.objects.filter(
            organisation=organisation
        ).order_by('-created_at')[:limit]:
            transactions.append({
                'type': 'invoice',
                'number': invoice.invoice_number,
                'name': invoice.customer.name,
                'amount': invoice.total,
                'date': invoice.invoice_date,
                'status': invoice.status,
                'url': f'/receivables/invoices/{invoice.id}/',
            })

        # Recent bills
        for bill in Bill.objects.filter(
            organisation=organisation
        ).order_by('-created_at')[:limit]:
            transactions.append({
                'type': 'bill',
                'number': bill.bill_number,
                'name': bill.vendor.name,
                'amount': bill.total,
                'date': bill.bill_date,
                'status': bill.status,
                'url': f'/payables/bills/{bill.id}/',
            })

        # Recent journal entries
        for entry in JournalEntry.objects.filter(
            organisation=organisation,
            status='posted'
        ).order_by('-posted_at')[:limit]:
            transactions.append({
                'type': 'journal',
                'number': entry.entry_number,
                'name': entry.description[:50],
                'amount': entry.total_debit,
                'date': entry.date,
                'status': entry.status,
                'url': f'/ledger/entries/{entry.id}/',
            })

        # Sort by date and limit
        transactions.sort(key=lambda x: x['date'], reverse=True)
        return transactions[:limit]

    @staticmethod
    def get_ap_due_soon(organisation: Organisation, days: int = 30) -> list:
        """Get payables due in the next N days."""
        today = timezone.now().date()
        end_date = today + timedelta(days=days)

        return Bill.objects.filter(
            organisation=organisation,
            status__in=['open', 'partial'],
            due_date__gte=today,
            due_date__lte=end_date
        ).select_related('vendor').order_by('due_date')

    @staticmethod
    def get_ar_aging_summary(organisation: Organisation) -> dict:
        """Get accounts receivable aging summary."""
        today = timezone.now().date()

        aging = {
            'current': Decimal('0'),
            'days_30': Decimal('0'),
            'days_60': Decimal('0'),
            'days_90': Decimal('0'),
            'over_90': Decimal('0'),
        }

        invoices = Invoice.objects.filter(
            organisation=organisation,
            status__in=['sent', 'partial'],
            balance__gt=0
        )

        for invoice in invoices:
            days_overdue = (today - invoice.due_date).days

            if days_overdue <= 0:
                aging['current'] += invoice.balance
            elif days_overdue <= 30:
                aging['days_30'] += invoice.balance
            elif days_overdue <= 60:
                aging['days_60'] += invoice.balance
            elif days_overdue <= 90:
                aging['days_90'] += invoice.balance
            else:
                aging['over_90'] += invoice.balance

        return aging
