from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from organisations.models import Organisation
from typing import Optional
import uuid


class AccountTypeManager(models.Manager):
    """Manager for AccountType model."""

    def get_by_natural_key(self, name, organisation_id):
        return self.get(name=name, organisation_id=organisation_id)


class AccountType(models.Model):
    """
    Account types following standard accounting principles.
    Five main types: Assets, Liabilities, Equity, Income, Expenses.
    """

    class Name(models.TextChoices):
        ASSET = 'asset', _('Asset')
        LIABILITY = 'liability', _('Liability')
        EQUITY = 'equity', _('Equity')
        INCOME = 'income', _('Income')
        EXPENSE = 'expense', _('Expense')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='account_types'
    )
    name = models.CharField(_('Name'), max_length=20, choices=Name.choices)
    description = models.TextField(_('Description'), blank=True)

    # Normal balance (debit increases, credit decreases)
    normal_balance = models.CharField(
        _('Normal Balance'),
        max_length=10,
        choices=[
            ('debit', _('Debit')),
            ('credit', _('Credit')),
        ],
        default='debit'
    )

    is_active = models.BooleanField(_('Is Active'), default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AccountTypeManager()

    class Meta:
        db_table = 'account_types'
        verbose_name = _('Account Type')
        verbose_name_plural = _('Account Types')
        constraints = [
            models.UniqueConstraint(
                fields=['organisation', 'name'],
                name='unique_account_type_per_org'
            )
        ]
        ordering = ['name']

    def __str__(self):
        return self.get_name_display()

    def natural_key(self):
        return (self.name, self.organisation_id)

    @property
    def is_debit_balance(self):
        """Returns True if normal balance is debit."""
        return self.normal_balance == 'debit'


class AccountCategory(models.Model):
    """
    Account categories within types for organization.
    Examples: Current Assets, Fixed Assets, Current Liabilities, etc.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='account_categories'
    )
    account_type = models.ForeignKey(
        AccountType,
        on_delete=models.CASCADE,
        related_name='categories'
    )
    name = models.CharField(_('Name'), max_length=100)
    code = models.CharField(_('Code'), max_length=10, blank=True)
    sequence = models.IntegerField(_('Sequence'), default=0)
    is_active = models.BooleanField(_('Is Active'), default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'account_categories'
        verbose_name = _('Account Category')
        verbose_name_plural = _('Account Categories')
        constraints = [
            models.UniqueConstraint(
                fields=['organisation', 'code'],
                condition=models.Q(code__gt=''),
                name='unique_category_code_per_org'
            )
        ]
        ordering = ['sequence', 'name']

    def __str__(self):
        return self.name


class Currency(models.Model):
    """Supported currencies for multi-currency accounting."""

    code = models.CharField(_('Code'), max_length=3, primary_key=True)
    name = models.CharField(_('Name'), max_length=50)
    symbol = models.CharField(_('Symbol'), max_length=5)
    is_active = models.BooleanField(_('Is Active'), default=True)
    decimal_places = models.IntegerField(_('Decimal Places'), default=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'currencies'
        verbose_name = _('Currency')
        verbose_name_plural = _('Currencies')
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class AccountManager(models.Manager):
    """Manager for Account model with tenant-aware queries."""

    def get_queryset(self):
        return super().get_queryset()

    def active(self):
        return self.get_queryset().filter(is_active=True)

    def by_type(self, account_type):
        return self.get_queryset().filter(account_type=account_type)

    def by_category(self, category):
        return self.get_queryset().filter(category=category)

    def leaf_accounts(self):
        """Get accounts that are not parents (can have transactions)."""
        return self.get_queryset().filter(children__isnull=True, allow_transactions=True)

    def root_accounts(self):
        """Get top-level accounts (no parent)."""
        return self.get_queryset().filter(parent__isnull=True)

    def bank_accounts(self):
        """Get all bank accounts."""
        return self.get_queryset().filter(is_bank_account=True, is_active=True)

    def receivable_accounts(self):
        """Get accounts receivable related accounts."""
        return self.get_queryset().filter(
            account_type__name=AccountType.Name.ASSET,
            name__icontains='receivable'
        )

    def payable_accounts(self):
        """Get accounts payable related accounts."""
        return self.get_queryset().filter(
            account_type__name=AccountType.Name.LIABILITY,
            name__icontains='payable'
        )


class Account(models.Model):
    """
    Chart of Accounts - The foundation of double-entry accounting.
    Hierarchical structure with support for grouping and reporting.
    """

    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        INACTIVE = 'inactive', _('Inactive')
        ARCHIVED = 'archived', _('Archived')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='accounts'
    )

    # Classification
    account_type = models.ForeignKey(
        AccountType,
        on_delete=models.PROTECT,
        related_name='accounts',
        verbose_name=_('Account Type')
    )
    category = models.ForeignKey(
        AccountCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='accounts',
        verbose_name=_('Category')
    )

    # Account details
    code = models.CharField(_('Account Code'), max_length=20)
    name = models.CharField(_('Account Name'), max_length=255)
    description = models.TextField(_('Description'), blank=True)

    # Hierarchy
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        verbose_name=_('Parent Account')
    )
    level = models.IntegerField(_('Level'), default=0)

    # Settings
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.ACTIVE)
    is_active = models.BooleanField(_('Is Active'), default=True)
    is_header = models.BooleanField(_('Is Header'), default=False, help_text=_('Header accounts group other accounts'))
    allow_transactions = models.BooleanField(_('Allow Transactions'), default=True, help_text=_('Only leaf accounts can have transactions'))
    is_bank_account = models.BooleanField(_('Is Bank Account'), default=False)
    is_reconcilable = models.BooleanField(_('Is Reconcilable'), default=False, help_text=_('Can be reconciled with bank statements'))
    is_tax_account = models.BooleanField(_('Tax Account'), default=False)

    # Currency support
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        default='USD',
        verbose_name=_('Currency')
    )

    # Tax settings
    tax_rate = models.DecimalField(_('Tax Rate'), max_digits=5, decimal_places=2, default=0)
    tax_code = models.CharField(_('Tax Code'), max_length=50, blank=True)

    # Balances (stored for performance)
    opening_balance = models.DecimalField(_('Opening Balance'), max_digits=20, decimal_places=2, default=0)
    current_balance = models.DecimalField(_('Current Balance'), max_digits=20, decimal_places=2, default=0)
    period_debit = models.DecimalField(_('Period Debit'), max_digits=20, decimal_places=2, default=0)
    period_credit = models.DecimalField(_('Period Credit'), max_digits=20, decimal_places=2, default=0)

    # Metadata
    tags = models.JSONField(_('Tags'), default=list, blank=True)
    sequence = models.IntegerField(_('Sequence'), default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AccountManager()

    class Meta:
        db_table = 'accounts'
        verbose_name = _('Account')
        verbose_name_plural = _('Accounts')
        constraints = [
            models.UniqueConstraint(
                fields=['organisation', 'code'],
                name='unique_account_code_per_org'
            )
        ]
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def save(self, *args, **kwargs):
        # Calculate level based on parent
        if self.parent:
            self.level = self.parent.level + 1
        else:
            self.level = 0

        # Header accounts cannot have transactions
        if self.is_header:
            self.allow_transactions = False

        super().save(*args, **kwargs)

    @property
    def is_debit_account(self):
        """Returns True if this is a debit-balance account."""
        return self.account_type.is_debit_balance

    @property
    def formatted_code(self):
        """Format the account code with parent codes."""
        if self.parent:
            return f"{self.parent.formatted_code}.{self.code}"
        return self.code

    def get_balance(self, as_of=None):
        """Calculate the account balance as of a date."""
        from django.utils import timezone
        from django.db.models import Sum

        if as_of is None:
            as_of = timezone.now().date()

        balance = self.opening_balance

        transactions = self.debit_entries.filter(entry__date__lte=as_of).aggregate(
            total=Sum('amount')
        )['total'] or 0
        balance += transactions

        transactions = self.credit_entries.filter(entry__date__lte=as_of).aggregate(
            total=Sum('amount')
        )['total'] or 0
        balance -= transactions

        # For credit-balance accounts, reverse
        if not self.is_debit_account:
            balance = -balance

        return balance

    def update_balance(self):
        """Update current balance from transactions."""
        from django.db.models import Sum, F

        debit_total = self.debit_entries.aggregate(total=Sum('amount'))['total'] or 0
        credit_total = self.credit_entries.aggregate(total=Sum('amount'))['total'] or 0

        if self.is_debit_account:
            self.current_balance = self.opening_balance + debit_total - credit_total
        else:
            self.current_balance = self.opening_balance + credit_total - debit_total

        self.period_debit = debit_total
        self.period_credit = credit_total
        self.save(update_fields=['current_balance', 'period_debit', 'period_credit'])


class FiscalYear(models.Model):
    """Fiscal year management for period-based accounting."""

    class Status(models.TextChoices):
        OPEN = 'open', _('Open')
        CLOSED = 'closed', _('Closed')
        ADJUSTING = 'adjusting', _('Adjusting Period')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='fiscal_years'
    )

    name = models.CharField(_('Name'), max_length=50)
    start_date = models.DateField(_('Start Date'))
    end_date = models.DateField(_('End Date'))
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.OPEN)

    # Closing entries
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='closed_fiscal_years'
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    is_adjusting = models.BooleanField(_('Is Adjusting Period'), default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fiscal_years'
        verbose_name = _('Fiscal Year')
        verbose_name_plural = _('Fiscal Years')
        ordering = ['-start_date']

    def __str__(self):
        return self.name

    @property
    def is_open(self):
        return self.status == self.Status.OPEN

    def close(self, closed_by):
        """Close a fiscal year."""
        from django.utils import timezone

        self.status = self.Status.CLOSED
        self.closed_by = closed_by
        self.closed_at = timezone.now()
        self.save()


class FiscalPeriod(models.Model):
    """Individual periods within a fiscal year (typically months)."""

    class Status(models.TextChoices):
        OPEN = 'open', _('Open')
        CLOSED = 'closed', _('Closed')
        LOCKED = 'locked', _('Locked')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    fiscal_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.CASCADE,
        related_name='periods'
    )
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='periods'
    )

    name = models.CharField(_('Name'), max_length=50)
    period_number = models.IntegerField(_('Period Number'))
    start_date = models.DateField(_('Start Date'))
    end_date = models.DateField(_('End Date'))
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.OPEN)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'fiscal_periods'
        verbose_name = _('Fiscal Period')
        verbose_name_plural = _('Fiscal Periods')
        ordering = ['start_date']
        constraints = [
            models.UniqueConstraint(
                fields=['organisation', 'start_date', 'end_date'],
                name='unique_period_dates'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.fiscal_year.name})"

    @property
    def is_open(self):
        return self.status == self.Status.OPEN and self.fiscal_year.is_open


class JournalEntry(models.Model):
    """
    Journal Entry - The core transaction in double-entry accounting.
    Each entry must balance (total debits = total credits).
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PENDING = 'pending', _('Pending Approval')
        POSTED = 'posted', _('Posted')
        VOIDED = 'voided', _('Voided')

    class EntryType(models.TextChoices):
        GENERAL = 'general', _('General')
        ADJUSTING = 'adjusting', _('Adjusting')
        CLOSING = 'closing', _('Closing')
        OPENING = 'opening', _('Opening')
        REVERSING = 'reversing', _('Reversing')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='journal_entries'
    )

    # Entry identification
    entry_number = models.CharField(_('Entry Number'), max_length=50, blank=True)
    reference = models.CharField(_('Reference'), max_length=100, blank=True)

    # Dates
    date = models.DateField(_('Entry Date'), db_index=True)
    fiscal_year = models.ForeignKey(
        FiscalYear,
        on_delete=models.PROTECT,
        related_name='entries'
    )
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        on_delete=models.PROTECT,
        related_name='entries'
    )

    # Classification
    entry_type = models.CharField(_('Entry Type'), max_length=10, choices=EntryType.choices, default=EntryType.GENERAL)
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.DRAFT)

    # Description
    description = models.TextField(_('Description'))
    memo = models.TextField(_('Memo'), blank=True)

    # Source tracking
    source_type = models.CharField(_('Source Type'), max_length=50, blank=True, help_text=_('e.g., Invoice, Bill, Payment'))
    source_id = models.UUIDField(_('Source ID'), null=True, blank=True)

    # Document attachments
    attachments = models.JSONField(_('Attachments'), default=list, blank=True)

    # Audit fields
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_journal_entries'
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posted_journal_entries'
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='voided_journal_entries'
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(_('Void Reason'), blank=True)

    # Reversal tracking
    reversing_entry = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='original_entry'
    )

    # Totals
    total_debit = models.DecimalField(_('Total Debit'), max_digits=20, decimal_places=2, default=0)
    total_credit = models.DecimalField(_('Total Credit'), max_digits=20, decimal_places=2, default=0)

    # Currency
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        default='USD'
    )

    # Approval workflow
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_journal_entries'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'journal_entries'
        verbose_name = _('Journal Entry')
        verbose_name_plural = _('Journal Entries')
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['organisation', 'date']),
            models.Index(fields=['organisation', 'status']),
            models.Index(fields=['organisation', 'entry_type']),
        ]

    def __str__(self):
        return f"{self.entry_number} - {self.date} - {self.description[:50]}"

    def save(self, *args, **kwargs):
        if not self.entry_number:
            self.entry_number = self._generate_entry_number()
        super().save(*args, **kwargs)

    def _generate_entry_number(self):
        """Generate a unique journal entry number."""
        from django.utils import timezone
        year = self.date.year if self.date else timezone.now().year
        prefix = f"JE-{year}-"
        last_entry = JournalEntry.objects.filter(
            organisation=self.organisation,
            entry_number__startswith=prefix
        ).order_by('-entry_number').first()

        if last_entry:
            try:
                number = int(last_entry.entry_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                number = 1
        else:
            number = 1

        return f"{prefix}{number:06d}"

    def is_balanced(self):
        """Check if the entry is balanced."""
        return abs(self.total_debit - self.total_credit) < 0.01

    def post(self, posted_by):
        """Post the journal entry."""
        from django.utils import timezone

        if self.status != self.Status.DRAFT:
            raise ValueError(_("Only draft entries can be posted."))

        if not self.is_balanced():
            raise ValueError(_("Entry must be balanced before posting."))

        if not self.lines.exists():
            raise ValueError(_("Entry must have at least one line."))

        self.status = self.Status.POSTED
        self.posted_by = posted_by
        self.posted_at = timezone.now()
        self.save()

        # Update account balances
        for line in self.lines.all():
            line.account.update_balance()

    def void(self, voided_by, reason=''):
        """Void the journal entry and create reversing entry."""
        from django.utils import timezone

        if self.status != self.Status.POSTED:
            raise ValueError(_("Only posted entries can be voided."))

        # Create reversing entry
        reversing = JournalEntry.objects.create(
            organisation=self.organisation,
            date=timezone.now().date(),
            fiscal_year=self.fiscal_year,
            fiscal_period=self.fiscal_period,
            entry_type=JournalEntry.EntryType.REVERSING,
            description=f"Reversing entry for {self.entry_number}: {self.description}",
            source_type='void',
            source_id=self.id,
            created_by=voided_by,
            status=JournalEntry.Status.POSTED,
            posted_by=voided_by,
            posted_at=timezone.now(),
            reversing_entry=self,
            currency=self.currency,
        )

        # Create reversing lines
        for line in self.lines.all():
            JournalEntryLine.objects.create(
                entry=reversing,
                account=line.account,
                debit_amount=line.credit_amount,
                credit_amount=line.debit_amount,
                description=f"Reversal of {line.description}",
            )

        # Update totals
        reversing.total_debit = self.total_credit
        reversing.total_credit = self.total_debit
        reversing.save()

        # Mark original as voided
        self.status = self.Status.VOIDED
        self.voided_by = voided_by
        self.voided_at = timezone.now()
        self.void_reason = reason
        self.save()

        # Update account balances
        for account in set(line.account for line in self.lines.all()):
            account.update_balance()


class JournalEntryLine(models.Model):
    """Individual line items in a journal entry."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name='lines'
    )

    # Account
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='debit_entries'
    )

    # Amounts
    debit_amount = models.DecimalField(_('Debit'), max_digits=20, decimal_places=2, default=0)
    credit_amount = models.DecimalField(_('Credit'), max_digits=20, decimal_places=2, default=0)

    # Description for this line
    description = models.CharField(_('Description'), max_length=255, blank=True)

    # Analytical dimensions
    department = models.ForeignKey(
        'organisations.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='journal_lines'
    )

    # Cost tracking
    cost_center = models.CharField(_('Cost Center'), max_length=50, blank=True)
    project = models.CharField(_('Project'), max_length=100, blank=True)

    # Reconciliation
    reconciled = models.BooleanField(_('Reconciled'), default=False)
    reconciled_date = models.DateField(null=True, blank=True)
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reconciled_lines'
    )

    # Tax tracking
    tax_code = models.CharField(_('Tax Code'), max_length=50, blank=True)
    tax_amount = models.DecimalField(_('Tax Amount'), max_digits=20, decimal_places=2, default=0)

    # Currency exchange (for multi-currency)
    currency = models.ForeignKey(
        Currency,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )
    exchange_rate = models.DecimalField(_('Exchange Rate'), max_digits=12, decimal_places=6, default=1)
    base_currency_amount = models.DecimalField(_('Base Currency Amount'), max_digits=20, decimal_places=2, default=0)

    sequence = models.IntegerField(_('Sequence'), default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'journal_entry_lines'
        verbose_name = _('Journal Entry Line')
        verbose_name_plural = _('Journal Entry Lines')
        ordering = ['sequence', 'account__code']

    def __str__(self):
        return f"{self.entry.entry_number} - {self.account.code}"

    @property
    def amount(self):
        """Return the non-zero amount."""
        return self.debit_amount or self.credit_amount

    @property
    def is_debit(self):
        """Return True if this is a debit line."""
        return self.debit_amount > 0

    def clean(self):
        """Validate that either debit or credit is set, not both."""
        from django.core.exceptions import ValidationError

        if self.debit_amount > 0 and self.credit_amount > 0:
            raise ValidationError(_('A line cannot have both debit and credit amounts.'))

        if self.debit_amount == 0 and self.credit_amount == 0:
            raise ValidationError(_('A line must have either a debit or credit amount.'))


class RecurringJournalEntry(models.Model):
    """Template for recurring journal entries."""

    class Frequency(models.TextChoices):
        DAILY = 'daily', _('Daily')
        WEEKLY = 'weekly', _('Weekly')
        MONTHLY = 'monthly', _('Monthly')
        QUARTERLY = 'quarterly', _('Quarterly')
        YEARLY = 'yearly', _('Yearly')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='recurring_entries'
    )

    name = models.CharField(_('Name'), max_length=255)
    description = models.TextField(_('Description'))

    frequency = models.CharField(_('Frequency'), max_length=10, choices=Frequency.choices)
    day_of_month = models.IntegerField(_('Day of Month'), default=1, help_text=_('Day to post the entry (1-28)'))

    # Start/end dates
    start_date = models.DateField(_('Start Date'))
    end_date = models.DateField(_('End Date'), null=True, blank=True)
    next_run_date = models.DateField(_('Next Run Date'), null=True, blank=True)

    is_active = models.BooleanField(_('Is Active'), default=True)

    # Template lines
    template_lines = models.JSONField(_('Template Lines'), default=list)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'recurring_journal_entries'
        verbose_name = _('Recurring Journal Entry')
        verbose_name_plural = _('Recurring Journal Entries')
        ordering = ['name']

    def __str__(self):
        return self.name

    def should_run(self, date):
        """Check if the recurring entry should run on a given date."""
        if not self.is_active:
            return False

        if self.end_date and date > self.end_date:
            return False

        if date < self.start_date:
            return False

        return self.next_run_date == date

    def create_entry(self, date, user):
        """Create a journal entry from this template."""
        from ledger.services import JournalEntryService

        return JournalEntryService.create_from_recurring(self, date, user)
