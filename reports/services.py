from django.utils import timezone
from django.db.models import Sum, Q
from decimal import Decimal
from typing import Dict, List
from datetime import date
from dateutil.relativedelta import relativedelta

from ledger.models import Account, AccountType, JournalEntry, JournalEntryLine, FiscalYear, FiscalPeriod
from organisations.models import Organisation


class TrialBalanceService:
    """Service for generating Trial Balance reports."""

    @staticmethod
    def generate(organisation: Organisation, as_of: date = None, include_zero: bool = False) -> Dict:
        """Generate trial balance report."""
        from ledger.services import AccountBalanceService

        if as_of is None:
            as_of = timezone.now().date()

        trial_balance = AccountBalanceService.get_trial_balance(organisation, as_of)

        # Group by account type
        grouped = {}
        for account_data in trial_balance['accounts']:
            account = account_data['account']
            type_name = account.account_type.name

            if type_name not in grouped:
                grouped[type_name] = {
                    'accounts': [],
                    'total_debit': Decimal('0'),
                    'total_credit': Decimal('0'),
                }

            grouped[type_name]['accounts'].append(account_data)
            grouped[type_name]['total_debit'] += account_data['debit']
            grouped[type_name]['total_credit'] += account_data['credit']
            grouped[type_name]['difference'] = grouped[type_name]['total_debit'] - grouped[type_name]['total_credit']

        # Add type display names
        type_names = dict(AccountType.Name.choices)

        return {
            'as_of': as_of,
            'organisation': organisation,
            'grouped': grouped,
            'type_names': type_names,
            'total_debits': trial_balance['total_debits'],
            'total_credits': trial_balance['total_credits'],
            'is_balanced': abs(trial_balance['total_debits'] - trial_balance['total_credits']) < 0.01,
        }


class BalanceSheetService:
    """Service for generating Balance Sheet reports."""

    @staticmethod
    def generate(organisation: Organisation, as_of: date = None, period_type='monthly') -> Dict:
        """Generate balance sheet report."""
        if as_of is None:
            as_of = timezone.now().date()

        # Get previous period for comparison
        previous_date = as_of - relativedelta(months=1)

        # Get accounts with balance
        accounts = {}

        # Assets
        assets = Account.objects.filter(
            organisation=organisation,
            account_type__name='asset',
            is_active=True
        ).select_related('account_type', 'parent').order_by('code')

        current_assets = Decimal('0')
        non_current_assets = Decimal('0')

        for account in assets:
            balance = account.get_balance(as_of)
            if balance != Decimal('0'):
                accounts.setdefault('asset', []).append({
                    'account': account,
                    'balance': balance,
                })
                if account.code.startswith('1') and int(account.code) < 15:
                    current_assets += balance
                else:
                    non_current_assets += balance

        # Liabilities
        liabilities = Account.objects.filter(
            organisation=organisation,
            account_type__name='liability',
            is_active=True
        ).order_by('code')

        current_liabilities = Decimal('0')
        non_current_liabilities = Decimal('0')

        for account in liabilities:
            balance = account.get_balance(as_of)
            if balance != Decimal('0'):
                accounts.setdefault('liability', []).append({
                    'account': account,
                    'balance': balance,
                })
                if account.code.startswith('2') and int(account.code) < 25:
                    current_liabilities += balance
                else:
                    non_current_liabilities += balance

        # Equity
        equity_accounts = Account.objects.filter(
            organisation=organisation,
            account_type__name='equity',
            is_active=True
        ).order_by('code')

        total_equity = Decimal('0')
        for account in equity_accounts:
            balance = account.get_balance(as_of)
            if balance != Decimal('0'):
                accounts.setdefault('equity', []).append({
                    'account': account,
                    'balance': balance,
                })
                total_equity += balance

        # Calculate retained earnings
        revenue = Decimal('0')
        expenses = Decimal('0')

        revenue_accounts = Account.objects.filter(
            organisation=organisation,
            account_type__name='income',
            is_active=True
        )

        for account in revenue_accounts:
            revenue += account.period_credit

        expense_accounts = Account.objects.filter(
            organisation=organisation,
            account_type__name='expense',
            is_active=True
        )

        for account in expense_accounts:
            expenses += account.period_debit

        retained_earnings = revenue - expenses

        # Total calculations
        total_assets = current_assets + non_current_assets
        total_liabilities = current_liabilities + non_current_liabilities
        total_equity_and_liabilities = total_equity + total_liabilities

        return {
            'as_of': as_of,
            'organisation': organisation,
            'accounts': accounts,
            'current_assets': current_assets,
            'non_current_assets': non_current_assets,
            'total_assets': total_assets,
            'current_liabilities': current_liabilities,
            'non_current_liabilities': non_current_liabilities,
            'total_liabilities': total_liabilities,
            'total_equity': total_equity,
            'retained_earnings': retained_earnings,
            'total_equity_and_liabilities': total_equity_and_liabilities,
            'is_balanced': abs(total_assets - total_equity_and_liabilities) < 0.01,
        }


class IncomeStatementService:
    """Service for generating Income Statement (P&L) reports."""

    @staticmethod
    def generate(organisation: Organisation, start_date: date = None, end_date: date = None,
                 include_prev_period: bool = True, period_type: str = 'monthly') -> Dict:
        """Generate income statement report."""
        if end_date is None:
            end_date = timezone.now().date()

        if start_date is None:
            # Get fiscal period or default to month
            start_date = end_date.replace(day=1)

        # Previous period for comparison
        period_days = (end_date - start_date).days + 1
        previous_end = start_date - timedelta(days=1)
        previous_start = previous_end - timedelta(days=period_days)

        # Revenue
        revenue_accounts = Account.objects.filter(
            organisation=organisation,
            account_type__name='income',
            is_active=True
        ).order_by('code')

        revenue = []
        total_revenue = Decimal('0')
        total_revenue_prev = Decimal('0')

        for account in revenue_accounts:
            # Calculate period activity
            current = IncomeStatementService._get_account_activity(account, start_date, end_date)
            if current != Decimal('0'):
                prev = Decimal('0')
                if include_prev_period:
                    prev = IncomeStatementService._get_account_activity(account, previous_start, previous_end)

                revenue.append({
                    'account': account,
                    'current': current,
                    'previous': prev,
                    'change': current - prev if include_prev_period else Decimal('0'),
                })
                total_revenue += current
                total_revenue_prev += prev

        # Expenses
        expense_accounts = Account.objects.filter(
            organisation=organisation,
            account_type__name='expense',
            is_active=True
        ).order_by('code')

        expenses = []
        total_expenses = Decimal('0')
        total_expenses_prev = Decimal('0')

        for account in expense_accounts:
            current = IncomeStatementService._get_account_activity(account, start_date, end_date)
            if current != Decimal('0'):
                prev = Decimal('0')
                if include_prev_period:
                    prev = IncomeStatementService._get_account_activity(account, previous_start, previous_end)

                expenses.append({
                    'account': account,
                    'current': current,
                    'previous': prev,
                    'change': current - prev if include_prev_period else Decimal('0'),
                })
                total_expenses += current
                total_expenses_prev += prev

        # Gross profit and net income
        gross_profit = total_revenue - total_expenses
        net_income = gross_profit  # Simplified - add other income/expenses as needed

        return {
            'start_date': start_date,
            'end_date': end_date,
            'organisation': organisation,
            'period_type': period_type,
            'revenue': revenue,
            'total_revenue': total_revenue,
            'total_revenue_prev': total_revenue_prev,
            'expenses': expenses,
            'total_expenses': total_expenses,
            'total_expenses_prev': total_expenses_prev,
            'gross_profit': gross_profit,
            'net_income': net_income,
            'net_income_prev': gross_profit if include_prev_period else None,
        }

    @staticmethod
    def _get_account_activity(account: Account, start_date: date, end_date: date) -> Decimal:
        """Calculate account activity for a period."""
        lines = JournalEntryLine.objects.filter(
            account=account,
            entry__status=JournalEntry.Status.POSTED,
            entry__date__gte=start_date,
            entry__date__lte=end_date
        )

        if account.account_type.is_debit_balance:
            return lines.aggregate(
                total=Sum('debit_amount') - Sum('credit_amount')
            )['total'] or Decimal('0')
        else:
            return lines.aggregate(
                total=Sum('credit_amount') - Sum('debit_amount')
            )['total'] or Decimal('0')


class CashFlowService:
    """Service for generating Cash Flow Statement."""

    @staticmethod
    def generate(organisation: Organisation, start_date: date = None, end_date: date = None) -> Dict:
        """Generate cash flow statement using indirect method."""
        if end_date is None:
            end_date = timezone.now().date()

        if start_date is None:
            start_date = end_date.replace(day=1)

        # Operating Activities
        operating_activities = []

        # Net income
        income_statement = IncomeStatementService.generate(organisation, start_date, end_date, include_prev_period=False)
        net_income = income_statement['net_income']

        operating_activities.append({
            'description': 'Net Income',
            'amount': net_income,
        })

        # Adjustments for non-cash items
        # Depreciation
        depreciation_accounts = Account.objects.filter(
            organisation=organisation,
            code__in=['5150'],  # Depreciation Expense
        )

        depreciation = Decimal('0')
        for account in depreciation_accounts:
            depreciation += IncomeStatementService._get_account_activity(account, start_date, end_date)

        if depreciation > 0:
            operating_activities.append({
                'description': 'Depreciation Expense',
                'amount': depreciation,
            })

        # Changes in working capital
        # AR decrease = cash inflow
        # AP increase = cash inflow
        # These should be calculated from period changes

        total_operating = sum(a['amount'] for a in operating_activities)

        # Investing Activities
        investing_activities = []

        # Investing typically from fixed asset purchases/sales
        investing_accounts = Account.objects.filter(
            organisation=organisation,
            account_type__name='asset',
            code__startswith='15',  # PP&E
        )

        total_investing = sum(a['amount'] for a in investing_activities)

        # Financing Activities
        financing_activities = []

        # Debt and equity changes
        total_financing = sum(a['amount'] for a in financing_activities)

        # Net change in cash
        net_cash_change = total_operating + total_investing + total_financing

        # Beginning and ending cash
        cash_accounts = Account.objects.filter(
            organisation=organisation,
            is_bank_account=True
        )

        beginning_cash = Decimal('0')
        ending_cash = Decimal('0')

        for account in cash_accounts:
            beginning_cash += account.get_balance(start_date)
            ending_cash += account.get_balance(end_date)

        return {
            'start_date': start_date,
            'end_date': end_date,
            'organisation': organisation,
            'operating_activities': operating_activities,
            'total_operating': total_operating,
            'investing_activities': investing_activities,
            'total_investing': total_investing,
            'financing_activities': financing_activities,
            'total_financing': total_financing,
            'net_cash_change': net_cash_change,
            'beginning_cash': beginning_cash,
            'ending_cash': ending_cash,
        }


class AgedReceivablesService:
    """Service for Aged Receivables report."""

    @staticmethod
    def generate(organisation: Organisation, as_of: date = None) -> Dict:
        """Generate aged receivables report."""
        if as_of is None:
            as_of = timezone.now().date()

        from receivables.models import Invoice, Customer

        open_invoices = Invoice.objects.filter(
            organisation=organisation,
            status__in=['sent', 'partial'],
            balance__gt=0
        ).select_related('customer').order_by('customer', 'due_date')

        aging = {
            'current': Decimal('0'),
            'days_30': Decimal('0'),
            'days_60': Decimal('0'),
            'days_90': Decimal('0'),
            'over_90': Decimal('0'),
        }

        customer_aging = {}

        for invoice in open_invoices:
            days_overdue = (as_of - invoice.due_date).days

            # Determine aging bucket
            if days_overdue <= 0:
                bucket = 'current'
            elif days_overdue <= 30:
                bucket = 'days_30'
            elif days_overdue <= 60:
                bucket = 'days_60'
            elif days_overdue <= 90:
                bucket = 'days_90'
            else:
                bucket = 'over_90'

            # Add to totals
            aging[bucket] += invoice.balance

            # Add to customer aging
            customer_id = str(invoice.customer_id)
            if customer_id not in customer_aging:
                customer_aging[customer_id] = {
                    'customer': invoice.customer,
                    'current': Decimal('0'),
                    'days_30': Decimal('0'),
                    'days_60': Decimal('0'),
                    'days_90': Decimal('0'),
                    'over_90': Decimal('0'),
                    'total': Decimal('0'),
                    'invoices': [],
                }

            customer_aging[customer_id][bucket] += invoice.balance
            customer_aging[customer_id]['total'] += invoice.balance
            customer_aging[customer_id]['invoices'].append(invoice)

        aging['total'] = sum(aging.values())

        return {
            'as_of': as_of,
            'organisation': organisation,
            'aging': aging,
            'customer_aging': list(customer_aging.values()),
        }


class AgedPayablesService:
    """Service for Aged Payables report."""

    @staticmethod
    def generate(organisation: Organisation, as_of: date = None) -> Dict:
        """Generate aged payables report."""
        if as_of is None:
            as_of = timezone.now().date()

        from payables.models import Bill, Vendor

        open_bills = Bill.objects.filter(
            organisation=organisation,
            status__in=['open', 'partial'],
            balance__gt=0
        ).select_related('vendor').order_by('vendor', 'due_date')

        aging = {
            'current': Decimal('0'),
            'days_30': Decimal('0'),
            'days_60': Decimal('0'),
            'days_90': Decimal('0'),
            'over_90': Decimal('0'),
        }

        vendor_aging = {}

        for bill in open_bills:
            days_overdue = (as_of - bill.due_date).days

            if days_overdue <= 0:
                bucket = 'current'
            elif days_overdue <= 30:
                bucket = 'days_30'
            elif days_overdue <= 60:
                bucket = 'days_60'
            elif days_overdue <= 90:
                bucket = 'days_90'
            else:
                bucket = 'over_90'

            aging[bucket] += bill.balance

            vendor_id = str(bill.vendor_id)
            if vendor_id not in vendor_aging:
                vendor_aging[vendor_id] = {
                    'vendor': bill.vendor,
                    'current': Decimal('0'),
                    'days_30': Decimal('0'),
                    'days_60': Decimal('0'),
                    'days_90': Decimal('0'),
                    'over_90': Decimal('0'),
                    'total': Decimal('0'),
                    'bills': [],
                }

            vendor_aging[vendor_id][bucket] += bill.balance
            vendor_aging[vendor_id]['total'] += bill.balance
            vendor_aging[vendor_id]['bills'].append(bill)

        aging['total'] = sum(aging.values())

        return {
            'as_of': as_of,
            'organisation': organisation,
            'aging': aging,
            'vendor_aging': list(vendor_aging.values()),
        }
