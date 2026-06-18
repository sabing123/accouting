from django.db import transaction
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import timedelta
from typing import List, Dict, Optional
from decimal import Decimal
import calendar

from ledger.models import (
    Account, AccountType, AccountCategory, JournalEntry, JournalEntryLine,
    FiscalYear, FiscalPeriod, Currency, RecurringJournalEntry
)
from organisations.models import Organisation


class ChartOfAccountsService:
    """Service for managing Chart of Accounts."""

    DEFAULT_ACCOUNT_TYPES = [
        ('asset', 'Asset', 'debit'),
        ('liability', 'Liability', 'credit'),
        ('equity', 'Equity', 'credit'),
        ('income', 'Income', 'credit'),
        ('expense', 'Expense', 'debit'),
    ]

    DEFAULT_ACCOUNTS = [
        # Assets - 1000
        ('1000', 'Cash and Cash Equivalents', 'asset', True),
        ('1100', 'Accounts Receivable', 'asset', True),
        ('1110', 'Allowance for Doubtful Accounts', 'asset', False),  # Contra-asset
        ('1200', 'Inventory', 'asset', True),
        ('1300', 'Prepaid Expenses', 'asset', True),
        ('1400', 'Other Current Assets', 'asset', True),
        ('1500', 'Property, Plant and Equipment', 'asset', True),
        ('1510', 'Accumulated Depreciation', 'asset', False),  # Contra-asset
        ('1600', 'Intangible Assets', 'asset', True),
        ('1700', 'Other Non-Current Assets', 'asset', True),
        # Liabilities - 2000
        ('2000', 'Accounts Payable', 'liability', True),
        ('2100', 'Accrued Expenses', 'liability', True),
        ('2200', 'Short-term Debt', 'liability', True),
        ('2300', 'Deferred Revenue', 'liability', True),
        ('2400', 'Other Current Liabilities', 'liability', True),
        ('2500', 'Long-term Debt', 'liability', True),
        ('2600', 'Other Non-Current Liabilities', 'liability', True),
        # Equity - 3000
        ('3000', "Owner's Equity", 'equity', True),
        ('3100', 'Retained Earnings', 'equity', True),
        ('3200', 'Common Stock', 'equity', True),
        ('3300', 'Additional Paid-in Capital', 'equity', True),
        # Income - 4000
        ('4000', 'Revenue', 'income', True),
        ('4100', 'Sales Revenue', 'income', True),
        ('4200', 'Service Revenue', 'income', True),
        ('4300', 'Other Income', 'income', True),
        ('4400', 'Interest Income', 'income', True),
        ('4500', 'Gain on Sale of Assets', 'income', True),
        # Expenses - 5000
        ('5000', 'Cost of Goods Sold', 'expense', True),
        ('5100', 'Operating Expenses', 'expense', True),
        ('5110', 'Salaries and Wages', 'expense', True),
        ('5120', 'Rent Expense', 'expense', True),
        ('5130', 'Utilities Expense', 'expense', True),
        ('5140', 'Insurance Expense', 'expense', True),
        ('5150', 'Depreciation Expense', 'expense', True),
        ('5160', 'Professional Fees', 'expense', True),
        ('5170', 'Travel and Entertainment', 'expense', True),
        ('5180', 'Office Supplies', 'expense', True),
        ('5190', 'Marketing and Advertising', 'expense', True),
        ('5200', 'Interest Expense', 'expense', True),
        ('5300', 'Loss on Sale of Assets', 'expense', True),
    ]

    @classmethod
    def setup_default_chart_of_accounts(cls, organisation: Organisation) -> List[Account]:
        """Create default chart of accounts for a new organisation."""

        if Account.objects.filter(organisation=organisation).exists():
            return list(organisation.accounts.all())

        accounts = []

        with transaction.atomic():
            # Create default account types
            account_types = {}
            for name, display, balance in cls.DEFAULT_ACCOUNT_TYPES:
                account_type, _ = AccountType.objects.get_or_create(
                    organisation=organisation,
                    name=name,
                    defaults={
                        'normal_balance': balance,
                        'description': display
                    }
                )
                account_types[name] = account_type

            # Create default categories
            categories = {}
            category_data = {
                'asset': [('CA', 'Current Assets', 1), ('NCA', 'Non-Current Assets', 2)],
                'liability': [('CL', 'Current Liabilities', 1), ('NCL', 'Non-Current Liabilities', 2)],
                'equity': [('EQ', 'Equity', 1)],
                'income': [('REV', 'Revenue', 1), ('OI', 'Other Income', 2)],
                'expense': [('COGS', 'Cost of Goods Sold', 1), ('OPEX', 'Operating Expenses', 2), ('OI2', 'Other Expenses', 3)],
            }

            for type_name, cats in category_data.items():
                for code, name, seq in cats:
                    category, _ = AccountCategory.objects.get_or_create(
                        organisation=organisation,
                        account_type=account_types[type_name],
                        name=name,
                        defaults={'code': code, 'sequence': seq}
                    )
                    categories[f"{type_name}_{name}"] = category

            # Create default accounts
            for code, name, type_name, is_debit in cls.DEFAULT_ACCOUNTS:
                # Determine category
                cat_key = None
                if code.startswith('1'):
                    if code in ['1000', '1100', '1110', '1200', '1300', '1400']:
                        cat_key = 'asset_Current Assets'
                    else:
                        cat_key = 'asset_Non-Current Assets'
                elif code.startswith('2'):
                    if code in ['2000', '2100', '2200', '2300', '2400']:
                        cat_key = 'liability_Current Liabilities'
                    else:
                        cat_key = 'liability_Non-Current Liabilities'
                elif code.startswith('3'):
                    cat_key = 'equity_Equity'
                elif code.startswith('4'):
                    cat_key = 'income_Revenue'
                elif code.startswith('5'):
                    if code == '5000':
                        cat_key = 'expense_Cost of Goods Sold'
                    elif code in ['5200', '5300']:
                        cat_key = 'expense_Other Expenses'
                    else:
                        cat_key = 'expense_Operating Expenses'

                # Special accounts
                is_bank = code == '1000'
                is_reconcilable = code in ['1000', '1100']

                account = Account.objects.create(
                    organisation=organisation,
                    account_type=account_types[type_name],
                    category=categories.get(cat_key),
                    code=code,
                    name=name,
                    is_bank_account=is_bank,
                    is_reconcilable=is_reconcilable,
                )
                accounts.append(account)

            # Set up parent-child relationships
            parent_map = {
                '1000': ['1100', '1200', '1300', '1400', '1500', '1600', '1700'],
                '1500': ['1510'],
                '2000': ['2100', '2200', '2300', '2400', '2500', '2600'],
                '3000': ['3100', '3200', '3300'],
                '4000': ['4100', '4200', '4300', '4400', '4500'],
                '5000': ['5100', '5200', '5300'],
                '5100': ['5110', '5120', '5130', '5140', '5150', '5160', '5170', '5180', '5190'],
            }

            for parent_code, child_codes in parent_map.items():
                try:
                    parent = Account.objects.get(organisation=organisation, code=parent_code)
                    parent.is_header = True
                    parent.allow_transactions = False
                    parent.save()

                    for child_code in child_codes:
                        try:
                            child = Account.objects.get(organisation=organisation, code=child_code)
                            child.parent = parent
                            child.save()
                        except Account.DoesNotExist:
                            pass
                except Account.DoesNotExist:
                    pass

        return accounts

    @classmethod
    def create_account(cls, organisation: Organisation, code: str, name: str,
                       account_type: AccountType, **kwargs) -> Account:
        """Create a new account in the chart of accounts."""

        # Check for duplicate code
        if Account.objects.filter(organisation=organisation, code=code).exists():
            raise ValueError(f"Account with code {code} already exists.")

        account = Account.objects.create(
            organisation=organisation,
            code=code,
            name=name,
            account_type=account_type,
            **kwargs
        )
        return account

    @classmethod
    def move_account(cls, account: Account, new_parent: Optional[Account]) -> Account:
        """Move an account to a new parent."""
        account.parent = new_parent
        account.save()
        return account

    @classmethod
    def deactivate_account(cls, account: Account) -> Account:
        """Deactivate an account (soft delete)."""
        # Check if account has transactions in open periods
        has_transactions = JournalEntryLine.objects.filter(
            account=account,
            entry__status=JournalEntry.Status.POSTED
        ).exists()

        if has_transactions:
            # Can only deactivate, not delete
            account.status = Account.Status.ARCHIVED
            account.is_active = False
            account.save()
        else:
            account.delete()

        return account


class JournalEntryService:
    """Service for creating and managing journal entries."""

    @classmethod
    def create_entry(cls, organisation: Organisation, date, description: str,
                     lines: List[Dict], created_by, **kwargs) -> JournalEntry:
        """
        Create a new journal entry.

        Args:
            organisation: The organisation
            date: Entry date
            description: Entry description
            lines: List of dicts with 'account', 'debit', 'credit', 'description'
            created_by: User creating the entry
            **kwargs: Additional entry fields

        Returns:
            The created JournalEntry
        """
        # Validate balance
        total_debit = sum(Decimal(str(line.get('debit', 0))) for line in lines)
        total_credit = sum(Decimal(str(line.get('credit', 0))) for line in lines)

        if abs(total_debit - total_credit) > Decimal('0.01'):
            raise ValueError("Journal entry must be balanced (debits must equal credits).")

        # Get fiscal year and period
        fiscal_year = cls._get_fiscal_year(organisation, date)
        fiscal_period = cls._get_fiscal_period(organisation, date)

        with transaction.atomic():
            entry = JournalEntry.objects.create(
                organisation=organisation,
                date=date,
                description=description,
                fiscal_year=fiscal_year,
                fiscal_period=fiscal_period,
                created_by=created_by,
                status=JournalEntry.Status.DRAFT,
                total_debit=total_debit,
                total_credit=total_credit,
                **kwargs
            )

            # Create lines
            for idx, line_data in enumerate(lines):
                JournalEntryLine.objects.create(
                    entry=entry,
                    account_id=line_data['account'],
                    debit_amount=Decimal(str(line_data.get('debit', 0))),
                    credit_amount=Decimal(str(line_data.get('credit', 0))),
                    description=line_data.get('description', ''),
                    department_id=line_data.get('department'),
                    cost_center=line_data.get('cost_center', ''),
                    project=line_data.get('project', ''),
                    sequence=idx
                )

            return entry

    @classmethod
    def post_entry(cls, entry: JournalEntry, posted_by) -> JournalEntry:
        """Post a journal entry."""
        if entry.status not in [JournalEntry.Status.DRAFT, JournalEntry.Status.PENDING]:
            raise ValueError("Only draft or pending entries can be posted.")

        if not entry.is_balanced():
            raise ValueError("Entry must be balanced before posting.")

        if not entry.lines.exists():
            raise ValueError("Entry must have at least one line.")

        # Check period is open
        if not entry.fiscal_period.is_open:
            raise ValueError("Cannot post to a closed period.")

        entry.status = JournalEntry.Status.POSTED
        entry.posted_by = posted_by
        entry.posted_at = timezone.now()
        entry.save()

        # Update account balances
        for line in entry.lines.all():
            line.account.update_balance()

        return entry

    @classmethod
    def void_entry(cls, entry: JournalEntry, voided_by, reason: str = '') -> JournalEntry:
        """Void a posted journal entry."""
        entry.void(voided_by, reason)
        return entry

    @classmethod
    def create_from_recurring(cls, template: RecurringJournalEntry, date, user) -> JournalEntry:
        """Create a journal entry from a recurring template."""

        fiscal_year = cls._get_fiscal_year(template.organisation, date)
        fiscal_period = cls._get_fiscal_period(template.organisation, date)

        lines = []
        for line_data in template.template_lines:
            lines.append({
                'account': line_data['account_id'],
                'debit': line_data.get('debit', 0),
                'credit': line_data.get('credit', 0),
                'description': line_data.get('description', ''),
            })

        entry = cls.create_entry(
            organisation=template.organisation,
            date=date,
            description=f"{template.name} - {template.description}",
            lines=lines,
            created_by=user,
            entry_type=JournalEntry.EntryType.GENERAL,
        )

        # Post immediately
        cls.post_entry(entry, user)

        # Update next run date
        template.next_run_date = cls._calculate_next_run(template, date)
        template.save()

        return entry

    @classmethod
    def _get_fiscal_year(cls, organisation: Organisation, date) -> FiscalYear:
        """Get the fiscal year for a given date."""
        fiscal_year = FiscalYear.objects.filter(
            organisation=organisation,
            start_date__lte=date,
            end_date__gte=date
        ).first()

        if not fiscal_year:
            # Create fiscal year automatically
            year_start_month = organisation.fiscal_year_start_month
            year = date.year

            start_date = timezone.datetime(year, year_start_month, 1).date()
            if year_start_month > 1:
                end_year = year + 1
            else:
                end_year = year

            _, last_day = calendar.monthrange(end_year, year_start_month - 1 if year_start_month > 1 else 12)
            end_date = timezone.datetime(end_year, year_start_month - 1 if year_start_month > 1 else 12, last_day).date()

            fiscal_year = FiscalYear.objects.create(
                organisation=organisation,
                name=f"FY {year}",
                start_date=start_date,
                end_date=end_date
            )

            # Create periods
            cls._create_periods(fiscal_year, organisation)

        return fiscal_year

    @classmethod
    def _get_fiscal_period(cls, organisation: Organisation, date) -> FiscalPeriod:
        """Get the fiscal period for a given date."""
        period = FiscalPeriod.objects.filter(
            organisation=organisation,
            start_date__lte=date,
            end_date__gte=date
        ).first()

        if not period:
            fiscal_year = cls._get_fiscal_year(organisation, date)
            period = FiscalPeriod.objects.filter(
                organisation=organisation,
                start_date__lte=date,
                end_date__gte=date
            ).first()

        return period

    @classmethod
    def _create_periods(cls, fiscal_year: FiscalYear, organisation: Organisation):
        """Create monthly periods for a fiscal year."""
        current_date = fiscal_year.start_date
        period_num = 1

        while current_date <= fiscal_year.end_date:
            # Get last day of month
            last_day = calendar.monthrange(current_date.year, current_date.month)[1]
            end_date = current_date.replace(day=last_day)

            if end_date > fiscal_year.end_date:
                end_date = fiscal_year.end_date

            FiscalPeriod.objects.create(
                fiscal_year=fiscal_year,
                organisation=organisation,
                name=current_date.strftime('%B %Y'),
                period_number=period_num,
                start_date=current_date,
                end_date=end_date
            )

            # Move to next month
            period_num += 1
            current_date = (end_date + timedelta(days=1)).replace(day=1)

    @classmethod
    def _calculate_next_run(cls, template: RecurringJournalEntry, current_date) -> Optional:
        """Calculate the next run date for a recurring entry."""
        from dateutil.relativedelta import relativedelta

        if template.end_date and current_date > template.end_date:
            return None

        deltas = {
            RecurringJournalEntry.Frequency.DAILY: relativedelta(days=1),
            RecurringJournalEntry.Frequency.WEEKLY: relativedelta(weeks=1),
            RecurringJournalEntry.Frequency.MONTHLY: relativedelta(months=1),
            RecurringJournalEntry.Frequency.QUARTERLY: relativedelta(months=3),
            RecurringJournalEntry.Frequency.YEARLY: relativedelta(years=1),
        }

        delta = deltas.get(template.frequency)
        if delta:
            next_date = current_date + delta
            if template.end_date and next_date > template.end_date:
                return None
            return next_date

        return None


class AccountBalanceService:
    """Service for calculating and updating account balances."""

    @classmethod
    def get_trial_balance(cls, organisation: Organisation, as_of: = None) -> Dict:
        """
        Generate a trial balance as of a specific date.

        Returns dict with accounts and their debit/credit balances.
        """
        if as_of is None:
            as_of = timezone.now().date()

        accounts = Account.objects.filter(
            organisation=organisation,
            is_active=True,
            allow_transactions=True
        ).select_related('account_type')

        trial_balance = {
            'accounts': [],
            'total_debits': Decimal('0'),
            'total_credits': Decimal('0'),
            'as_of': as_of,
        }

        for account in accounts:
            balance = account.get_balance(as_of)

            if abs(balance) > Decimal('0.01'):
                is_debit = account.is_debit_account
                debit = balance if is_debit else Decimal('0')
                credit = abs(balance) if not is_debit else Decimal('0')

                trial_balance['accounts'].append({
                    'account': account,
                    'debit': debit,
                    'credit': credit,
                })
                trial_balance['total_debits'] += debit
                trial_balance['total_credits'] += credit

        return trial_balance

    @classmethod
    def get_account_activity(cls, account: Account, start_date, end_date) -> List[Dict]:
        """Get all activity for an account within a date range."""
        lines = JournalEntryLine.objects.filter(
            account=account,
            entry__date__gte=start_date,
            entry__date__lte=end_date,
            entry__status=JournalEntry.Status.POSTED
        ).select_related('entry').order_by('entry__date', 'entry__created_at')

        activity = []
        running_balance = account.opening_balance

        for line in lines:
            if line.is_debit:
                running_balance += line.debit_amount
            else:
                running_balance -= line.credit_amount

            activity.append({
                'date': line.entry.date,
                'entry_number': line.entry.entry_number,
                'description': line.description or line.entry.description,
                'debit': line.debit_amount,
                'credit': line.credit_amount,
                'balance': running_balance if account.is_debit_account else -running_balance,
            })

        return activity

    @classmethod
    def recalculate_all_balances(cls, organisation: Organisation):
        """Recalculate all account balances from transactions."""
        accounts = Account.objects.filter(organisation=organisation)

        for account in accounts:
            account.update_balance()
