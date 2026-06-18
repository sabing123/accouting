from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from organisations.models import Organisation
from decimal import Decimal
import uuid


class BankAccountManager(models.Manager):
    """Manager for BankAccount model."""

    def get_queryset(self):
        return super().get_queryset()

    def active(self):
        return self.get_queryset().filter(is_active=True)


class BankAccount(models.Model):
    """
    Bank account for tracking cash and bank transactions.
    """

    class Type(models.TextChoices):
        CHECKING = 'checking', _('Checking')
        SAVINGS = 'savings', _('Savings')
        MONEY_MARKET = 'money_market', _('Money Market')
        CREDIT_LINE = 'credit_line', _('Line of Credit')

    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        INACTIVE = 'inactive', _('Inactive')
        CLOSED = 'closed', _('Closed')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='bank_accounts'
    )

    # Account details
    name = models.CharField(_('Account Name'), max_length=255)
    bank_name = models.CharField(_('Bank Name'), max_length=255)
    account_number = models.CharField(_('Account Number'), max_length=50)
    routing_number = models.CharField(_('Routing Number'), max_length=50, blank=True)
    account_type = models.CharField(_('Account Type'), max_length=20, choices=Type.choices, default=Type.CHECKING)

    # GL Account link
    account = models.OneToOneField(
        'ledger.Account',
        on_delete=models.PROTECT,
        related_name='bank_account',
        verbose_name=_('GL Account')
    )

    # Currency
    currency = models.CharField(_('Currency'), max_length=3, default='USD')

    # Status
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.ACTIVE)
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Balances
    opening_balance = models.DecimalField(_('Opening Balance'), max_digits=20, decimal_places=2, default=0)
    current_balance = models.DecimalField(_('Current Balance'), max_digits=20, decimal_places=2, default=0)

    # Last reconciliation
    last_reconciled_date = models.DateField(_('Last Reconciled Date'), null=True, blank=True)
    last_reconciled_balance = models.DecimalField(_('Last Reconciled Balance'), max_digits=20, decimal_places=2, default=0)

    # Metadata
    notes = models.TextField(_('Notes'), blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BankAccountManager()

    class Meta:
        db_table = 'bank_accounts'
        verbose_name = _('Bank Account')
        verbose_name_plural = _('Bank Accounts')
        ordering = ['name']

    def __str__(self):
        return f"{self.bank_name} - {self.name} ({self.account_number[-4:]})"

    @property
    def masked_account_number(self):
        """Return masked account number."""
        if len(self.account_number) > 4:
            return f"****{self.account_number[-4:]}"
        return self.account_number

    def update_balance(self):
        """Update current balance from transactions."""
        from django.db.models import Sum, Q
        from ledger.models import JournalEntryLine
        entries = JournalEntryLine.objects.filter(account=self.account)

        total_debits = entries.aggregate(total=Sum('debit_amount'))['total'] or Decimal('0')
        total_credits = entries.aggregate(total=Sum('credit_amount'))['total'] or Decimal('0')

        # Bank accounts are asset accounts, so debits increase balance
        self.current_balance = self.opening_balance + total_debits - total_credits
        self.save(update_fields=['current_balance'])


class BankTransaction(models.Model):
    """
    Imported bank transactions for reconciliation.
    """

    class TransactionType(models.TextChoices):
        DEBIT = 'debit', _('Debit (Withdrawal)')
        CREDIT = 'credit', _('Credit (Deposit)')

    class Status(models.TextChoices):
        UNMATCHED = 'unmatched', _('Unmatched')
        MATCHED = 'matched', _('Matched')
        RECONCILED = 'reconciled', _('Reconciled')
        IGNORED = 'ignored', _('Ignored')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.CASCADE,
        related_name='transactions'
    )

    # Transaction details
    transaction_date = models.DateField(_('Transaction Date'))
    value_date = models.DateField(_('Value Date'), null=True, blank=True)
    amount = models.DecimalField(_('Amount'), max_digits=20, decimal_places=2)
    transaction_type = models.CharField(
        _('Transaction Type'),
        max_length=10,
        choices=TransactionType.choices
    )

    # Description from bank
    description = models.CharField(_('Description'), max_length=500, blank=True)
    reference = models.CharField(_('Reference'), max_length=100, blank=True)
    bank_reference = models.CharField(_('Bank Reference'), max_length=100, blank=True)

    # Status
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.UNMATCHED)

    # Matching
    matched_journal_line = models.ForeignKey(
        'ledger.JournalEntryLine',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bank_transactions'
    )

    # Import reference
    import_batch = models.ForeignKey(
        'BankTransactionImport',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions'
    )

    # Notes
    notes = models.TextField(_('Notes'), blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bank_transactions'
        verbose_name = _('Bank Transaction')
        verbose_name_plural = _('Bank Transactions')
        ordering = ['-transaction_date', '-created_at']
        indexes = [
            models.Index(fields=['bank_account', 'transaction_date']),
            models.Index(fields=['bank_account', 'status']),
        ]

    def __str__(self):
        return f"{self.transaction_date} - {self.amount} - {self.description[:30]}"

    @property
    def is_debit(self):
        return self.transaction_type == self.TransactionType.DEBIT

    @property
    def is_reconciled(self):
        return self.status == self.Status.RECONCILED


class BankTransactionImport(models.Model):
    """Track bank statement imports."""

    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        PROCESSING = 'processing', _('Processing')
        COMPLETED = 'completed', _('Completed')
        FAILED = 'failed', _('Failed')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.CASCADE,
        related_name='imports'
    )

    filename = models.CharField(_('Filename'), max_length=255)
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.PENDING)

    statement_from_date = models.DateField(_('Statement From Date'))
    statement_to_date = models.DateField(_('Statement To Date'))
    statement_balance = models.DecimalField(_('Statement Balance'), max_digits=20, decimal_places=2)

    total_transactions = models.IntegerField(_('Total Transactions'), default=0)
    total_debit = models.DecimalField(_('Total Debit'), max_digits=20, decimal_places=2, default=0)
    total_credit = models.DecimalField(_('Total Credit'), max_digits=20, decimal_places=2, default=0)

    # File content
    raw_content = models.TextField(_('Raw Content'), blank=True)

    # Error tracking
    error_message = models.TextField(_('Error Message'), blank=True)

    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'bank_transaction_imports'
        verbose_name = _('Bank Transaction Import')
        verbose_name_plural = _('Bank Transaction Imports')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.filename} - {self.bank_account.name}"


class BankReconciliation(models.Model):
    """
    Bank statement reconciliation record.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = 'in_progress', _('In Progress')
        COMPLETED = 'completed', _('Completed')
        VOIDED = 'voided', _('Voided')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bank_account = models.ForeignKey(
        BankAccount,
        on_delete=models.CASCADE,
        related_name='reconciliations'
    )

    # Statement info
    statement_date = models.DateField(_('Statement Date'))
    statement_balance = models.DecimalField(_('Statement Balance'), max_digits=20, decimal_places=2)

    # Book balance
    book_balance = models.DecimalField(_('Book Balance'), max_digits=20, decimal_places=2)

    # Outstandings
    deposits_in_transit = models.DecimalField(_('Deposits in Transit'), max_digits=20, decimal_places=2, default=0)
    outstanding_checks = models.DecimalField(_('Outstanding Checks'), max_digits=20, decimal_places=2, default=0)

    # Adjustments
    adjustments = models.DecimalField(_('Adjustments'), max_digits=20, decimal_places=2, default=0)
    adjusted_book_balance = models.DecimalField(_('Adjusted Book Balance'), max_digits=20, decimal_places=2)

    # Difference (should be zero)
    difference = models.DecimalField(_('Difference'), max_digits=20, decimal_places=2, default=0)

    # Status
    status = models.CharField(_('Status'), max_length=20, choices=Status.choices, default=Status.IN_PROGRESS)

    # Audit
    reconciled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='bank_reconciliations'
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bank_reconciliations'
        verbose_name = _('Bank Reconciliation')
        verbose_name_plural = _('Bank Reconciliations')
        ordering = ['-statement_date']

    def __str__(self):
        return f"{self.bank_account.name} - {self.statement_date}"

    @property
    def is_balanced(self):
        return abs(self.difference) < Decimal('0.01')

    def calculate_difference(self):
        """Calculate the reconciliation difference."""
        # Adjusted book balance = Book balance + deposits in transit - outstanding checks + adjustments
        self.adjusted_book_balance = self.book_balance + self.deposits_in_transit - self.outstanding_checks + self.adjustments

        # Difference = Statement balance - Adjusted book balance
        self.difference = self.statement_balance - self.adjusted_book_balance

        return self.difference


class ReconciledLine(models.Model):
    """Lines reconciled during a bank reconciliation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reconciliation = models.ForeignKey(
        BankReconciliation,
        on_delete=models.CASCADE,
        related_name='reconciled_lines'
    )

    journal_line = models.ForeignKey(
        'ledger.JournalEntryLine',
        on_delete=models.CASCADE,
        related_name='reconciliations'
    )

    bank_transaction = models.ForeignKey(
        BankTransaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reconciliations'
    )

    reconciled_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'reconciled_lines'
        verbose_name = _('Reconciled Line')
        verbose_name_plural = _('Reconciled Lines')

    def __str__(self):
        return f"Reconciled: {self.journal_line}"


class Transfer(models.Model):
    """Bank account transfers."""

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PENDING = 'pending', _('Pending')
        COMPLETED = 'completed', _('Completed')
        VOIDED = 'voided', _('Voided')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='bank_transfers'
    )

    transfer_number = models.CharField(_('Transfer Number'), max_length=50, blank=True)
    transfer_date = models.DateField(_('Transfer Date'))
    amount = models.DecimalField(_('Amount'), max_digits=20, decimal_places=2)

    from_account = models.ForeignKey(
        BankAccount,
        on_delete=models.CASCADE,
        related_name='outgoing_transfers'
    )
    to_account = models.ForeignKey(
        BankAccount,
        on_delete=models.CASCADE,
        related_name='incoming_transfers'
    )

    reference = models.CharField(_('Reference'), max_length=100, blank=True)
    memo = models.TextField(_('Memo'), blank=True)

    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.DRAFT)

    journal_entry = models.ForeignKey(
        'ledger.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_transfers'
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_transfers'
    )
    processed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bank_transfers'
        verbose_name = _('Bank Transfer')
        verbose_name_plural = _('Bank Transfers')
        ordering = ['-transfer_date']

    def __str__(self):
        return f"{self.transfer_number} - {self.from_account} to {self.to_account}"

    def save(self, *args, **kwargs):
        if not self.transfer_number:
            from django.utils import timezone
            year = self.transfer_date.year if self.transfer_date else timezone.now().year
            count = Transfer.objects.filter(organisation=self.organisation).count()
            self.transfer_number = f"TRF-{year}-{count + 1:06d}"
        super().save(*args, **kwargs)
