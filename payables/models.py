from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from organisations.models import Organisation
from django.utils import timezone
import uuid


class VendorManager(models.Manager):
    """Manager for Vendor model."""

    def get_queryset(self):
        return super().get_queryset()

    def active(self):
        return self.get_queryset().filter(is_active=True)

    def with_outstanding_balance(self):
        """Get vendors with outstanding bills."""
        return self.get_queryset().filter(
            bills__status__in=['open', 'partial'],
            bills__balance__gt=0
        ).distinct()


class Vendor(models.Model):
    """
    Vendor/Supplier model for tracking accounts payable.
    """

    class Status(models.TextChoices):
        ACTIVE = 'active', _('Active')
        INACTIVE = 'inactive', _('Inactive')
        ON_HOLD = 'on_hold', _('On Hold')

    class PaymentTerms(models.TextChoices):
        DUE_ON_RECEIPT = 'due_on_receipt', _('Due on Receipt')
        NET_15 = 'net_15', _('Net 15')
        NET_30 = 'net_30', _('Net 30')
        NET_45 = 'net_45', _('Net 45')
        NET_60 = 'net_60', _('Net 60')
        END_OF_MONTH = 'end_of_month', _('End of Month')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='vendors'
    )

    # Basic info
    vendor_number = models.CharField(_('Vendor Number'), max_length=50, blank=True)
    name = models.CharField(_('Name'), max_length=255)
    display_name = models.CharField(_('Display Name'), max_length=255, blank=True)
    contact_name = models.CharField(_('Contact Name'), max_length=255, blank=True)
    email = models.EmailField(_('Email'), blank=True)
    phone = models.CharField(_('Phone'), max_length=50, blank=True)
    website = models.URLField(_('Website'), blank=True)

    # Address
    address_line1 = models.CharField(_('Address Line 1'), max_length=255, blank=True)
    address_line2 = models.CharField(_('Address Line 2'), max_length=255, blank=True)
    city = models.CharField(_('City'), max_length=100, blank=True)
    state_province = models.CharField(_('State/Province'), max_length=100, blank=True)
    postal_code = models.CharField(_('Postal Code'), max_length=20, blank=True)
    country = models.CharField(_('Country'), max_length=100, blank=True)

    # Tax & Payment
    tax_id = models.CharField(_('Tax ID'), max_length=50, blank=True)
    tax_code = models.CharField(_('Tax Code'), max_length=50, blank=True)
    payment_terms = models.CharField(
        _('Payment Terms'),
        max_length=20,
        choices=PaymentTerms.choices,
        default=PaymentTerms.NET_30
    )

    # Accounting defaults
    expense_account = models.ForeignKey(
        'ledger.Account',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vendors_default_expense'
    )
    payable_account = models.ForeignKey(
        'ledger.Account',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vendors_default_payable'
    )

    # Bank details (for payments)
    bank_name = models.CharField(_('Bank Name'), max_length=255, blank=True)
    bank_account_name = models.CharField(_('Bank Account Name'), max_length=255, blank=True)
    bank_account_number = models.CharField(_('Bank Account Number'), max_length=50, blank=True)
    bank_routing_number = models.CharField(_('Bank Routing Number'), max_length=50, blank=True)
    swift_code = models.CharField(_('SWIFT Code'), max_length=20, blank=True)
    iban = models.CharField(_('IBAN'), max_length=50, blank=True)

    # Status & Settings
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.ACTIVE)
    is_active = models.BooleanField(_('Is Active'), default=True)
    hold_reason = models.TextField(_('Hold Reason'), blank=True)

    # Notes
    notes = models.TextField(_('Notes'), blank=True)

    # Credit limit
    credit_limit = models.DecimalField(_('Credit Limit'), max_digits=20, decimal_places=2, default=0)

    # Currency
    currency = models.CharField(_('Currency'), max_length=3, default='USD')

    # Attachments
    attachments = models.JSONField(_('Attachments'), default=list, blank=True)

    # Metadata
    custom_fields = models.JSONField(_('Custom Fields'), default=dict, blank=True)
    tags = models.JSONField(_('Tags'), default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = VendorManager()

    class Meta:
        db_table = 'vendors'
        verbose_name = _('Vendor')
        verbose_name_plural = _('Vendors')
        ordering = ['name']

    def __str__(self):
        return self.display_name or self.name

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.name

        if not self.vendor_number:
            self.vendor_number = self._generate_vendor_number()

        super().save(*args, **kwargs)

    def _generate_vendor_number(self):
        prefix = "V-"
        count = Vendor.objects.filter(
            organisation=self.organisation
        ).count()
        return f"{prefix}{count + 1:05d}"

    @property
    def outstanding_balance(self):
        """Calculate outstanding balance from open bills."""
        from django.db.models import Sum
        return self.bills.filter(
            status__in=['open', 'partial']
        ).aggregate(
            total=Sum('balance')
        )['total'] or 0

    @property
    def total_billed(self):
        """Calculate total amount billed from all bills."""
        from django.db.models import Sum
        return self.bills.aggregate(total=Sum('total'))['total'] or 0

    def get_open_bills(self):
        """Get all open bills for this vendor."""
        return self.bills.filter(status__in=['open', 'partial']).order_by('-due_date')


class BillManager(models.Manager):
    """Manager for Bill model."""

    def get_queryset(self):
        return super().get_queryset()

    def open(self):
        return self.get_queryset().filter(status='open')

    def overdue(self):
        from django.utils import timezone
        return self.get_queryset().filter(
            status__in=['open', 'partial'],
            due_date__lt=timezone.now().date()
        )

    def due_this_week(self, organisation):
        from django.utils import timezone
        from datetime import timedelta
        today = timezone.now().date()
        week_end = today + timedelta(days=7)
        return self.get_queryset().filter(
            organisation=organisation,
            status__in=['open', 'partial'],
            due_date__lte=week_end,
            due_date__gte=today
        )


class Bill(models.Model):
    """
    Vendor Bill / Invoice for accounts payable tracking.
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PENDING = 'pending', _('Pending Approval')
        OPEN = 'open', _('Open')
        PARTIAL = 'partial', _('Partially Paid')
        PAID = 'paid', _('Paid')
        VOIDED = 'voided', _('Voided')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='bills'
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name='bills',
        verbose_name=_('Vendor')
    )

    # Bill details
    bill_number = models.CharField(_('Bill Number'), max_length=50, blank=True)
    vendor_invoice_number = models.CharField(_('Vendor Invoice Number'), max_length=50, blank=True)

    # Dates
    bill_date = models.DateField(_('Bill Date'), db_index=True)
    due_date = models.DateField(_('Due Date'))
    invoice_received_date = models.DateField(_('Invoice Received Date'), null=True, blank=True)

    # Currency
    currency = models.CharField(_('Currency'), max_length=3, default='USD')
    exchange_rate = models.DecimalField(_('Exchange Rate'), max_digits=12, decimal_places=6, default=1)

    # Status
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.DRAFT)

    # Description
    description = models.TextField(_('Description'), blank=True)
    notes = models.TextField(_('Notes'), blank=True)

    # Source
    purchase_order = models.CharField(_('PO Number'), max_length=50, blank=True)

    # Amounts
    subtotal = models.DecimalField(_('Subtotal'), max_digits=20, decimal_places=2, default=0)
    discount_amount = models.DecimalField(_('Discount Amount'), max_digits=20, decimal_places=2, default=0)
    tax_amount = models.DecimalField(_('Tax Amount'), max_digits=20, decimal_places=2, default=0)
    adjustment = models.DecimalField(_('Adjustment'), max_digits=20, decimal_places=2, default=0)
    total = models.DecimalField(_('Total'), max_digits=20, decimal_places=2, default=0)
    balance = models.DecimalField(_('Balance Due'), max_digits=20, decimal_places=2, default=0)

    # Discount early payment
    early_payment_discount = models.DecimalField(_('Early Payment Discount'), max_digits=20, decimal_places=2, default=0)
    early_payment_due_date = models.DateField(_('Early Payment Due Date'), null=True, blank=True)

    # Accounting
    journal_entry = models.ForeignKey(
        'ledger.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bills'
    )

    # Department/Project
    department = models.ForeignKey(
        'organisations.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    project = models.CharField(_('Project'), max_length=100, blank=True)

    # Approval workflow
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_bills'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_bills'
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posted_bills'
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='voided_bills'
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(_('Void Reason'), blank=True)

    # Attachments
    attachments = models.JSONField(_('Attachments'), default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BillManager()

    class Meta:
        db_table = 'bills'
        verbose_name = _('Bill')
        verbose_name_plural = _('Bills')
        ordering = ['-bill_date', '-created_at']
        indexes = [
            models.Index(fields=['organisation', 'status']),
            models.Index(fields=['organisation', 'due_date']),
        ]

    def __str__(self):
        return f"{self.bill_number} - {self.vendor.name}"

    def save(self, *args, **kwargs):
        if not self.bill_number:
            self.bill_number = self._generate_bill_number()

        # Calculate total and balance
        self.total = self.subtotal + self.tax_amount - self.discount_amount + self.adjustment

        if self.pk is None:
            self.balance = self.total
        else:
            # Update balance based on total and payments
            paid = self.payments.aggregate(total=models.Sum('amount'))['total'] or 0
            self.balance = self.total - paid

        super().save(*args, **kwargs)

    def _generate_bill_number(self):
        year = self.bill_date.year if self.bill_date else timezone.now().year
        prefix = f"BILL-{year}-"
        last_bill = Bill.objects.filter(
            organisation=self.organisation,
            bill_number__startswith=prefix
        ).order_by('-bill_number').first()

        if last_bill:
            try:
                number = int(last_bill.bill_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                number = 1
        else:
            number = 1

        return f"{prefix}{number:06d}"

    @property
    def is_overdue(self):
        from django.utils import timezone
        return self.status in ['open', 'partial'] and self.due_date < timezone.now().date()

    @property
    def days_overdue(self):
        if not self.is_overdue:
            return 0
        from django.utils import timezone
        return (timezone.now().date() - self.due_date).days

    @property
    def is_fully_paid(self):
        return self.status == 'paid' or abs(self.balance) < 0.01


class BillLine(models.Model):
    """Line items in a vendor bill."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bill = models.ForeignKey(
        Bill,
        on_delete=models.CASCADE,
        related_name='lines'
    )

    # Item details
    description = models.CharField(_('Description'), max_length=500)
    quantity = models.DecimalField(_('Quantity'), max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(_('Unit Price'), max_digits=20, decimal_places=2)

    # Account
    account = models.ForeignKey(
        'ledger.Account',
        on_delete=models.PROTECT,
        related_name='bill_lines'
    )

    # Tax
    tax_code = models.CharField(_('Tax Code'), max_length=50, blank=True)
    tax_rate = models.DecimalField(_('Tax Rate'), max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(_('Tax Amount'), max_digits=20, decimal_places=2, default=0)

    # Subtotal
    line_total = models.DecimalField(_('Line Total'), max_digits=20, decimal_places=2, default=0)

    # Department/Project
    department = models.ForeignKey(
        'organisations.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Analytical
    cost_center = models.CharField(_('Cost Center'), max_length=50, blank=True)
    project = models.CharField(_('Project'), max_length=100, blank=True)

    sequence = models.IntegerField(_('Sequence'), default=0)

    class Meta:
        db_table = 'bill_lines'
        verbose_name = _('Bill Line')
        verbose_name_plural = _('Bill Lines')
        ordering = ['sequence']

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        self.tax_amount = self.line_total * (self.tax_rate / 100)
        super().save(*args, **kwargs)


class PaymentMethodManager(models.Manager):
    """Manager for PaymentMethod model."""

    def get_queryset(self):
        return super().get_queryset()

    def active(self):
        return self.get_queryset().filter(is_active=True)


class PaymentMethod(models.Model):
    """Payment methods for vendor payments."""

    class Type(models.TextChoices):
        CHECK = 'check', _('Check')
        ACH = 'ach', _('ACH Transfer')
        WIRE = 'wire', _('Wire Transfer')
        CREDIT_CARD = 'credit_card', _('Credit Card')
        CASH = 'cash', _('Cash')
        OTHER = 'other', _('Other')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='payment_methods'
    )

    name = models.CharField(_('Name'), max_length=100)
    type = models.CharField(_('Type'), max_length=20, choices=Type.choices)
    is_default = models.BooleanField(_('Is Default'), default=False)
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Bank account for ACH/Check
    bank_account = models.ForeignKey(
        'banking.BankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PaymentMethodManager()

    class Meta:
        db_table = 'payment_methods'
        verbose_name = _('Payment Method')
        verbose_name_plural = _('Payment Methods')
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"


class Payment(models.Model):
    """
    Payment to vendor for accounts payable.
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PENDING = 'pending', _('Pending')
        APPROVED = 'approved', _('Approved')
        PROCESSED = 'processed', _('Processed')
        VOIDED = 'voided', _('Voided')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='vendor_payments'
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        related_name='payments',
        verbose_name=_('Vendor')
    )

    # Payment details
    payment_number = models.CharField(_('Payment Number'), max_length=50, blank=True)
    payment_date = models.DateField(_('Payment Date'), db_index=True)
    payment_method = models.ForeignKey(
        PaymentMethod,
        on_delete=models.PROTECT,
        verbose_name=_('Payment Method')
    )

    # Amount
    amount = models.DecimalField(_('Amount'), max_digits=20, decimal_places=2)
    currency = models.CharField(_('Currency'), max_length=3, default='USD')
    exchange_rate = models.DecimalField(_('Exchange Rate'), max_digits=12, decimal_places=6, default=1)

    # Status
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.DRAFT)

    # Check details
    check_number = models.CharField(_('Check Number'), max_length=50, blank=True)
    check_date = models.DateField(_('Check Date'), null=True, blank=True)

    # Reference
    reference = models.CharField(_('Reference'), max_length=100, blank=True)
    memo = models.TextField(_('Memo'), blank=True)

    # Bank account
    bank_account = models.ForeignKey(
        'banking.BankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Bank Account')
    )

    # Accounting
    journal_entry = models.ForeignKey(
        'ledger.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vendor_payments'
    )

    # Approval
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_payments'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_payments'
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_payments'
    )
    processed_at = models.DateTimeField(null=True, blank=True)

    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='voided_payments'
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(_('Void Reason'), blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'vendor_payments'
        verbose_name = _('Vendor Payment')
        verbose_name_plural = _('Vendor Payments')
        ordering = ['-payment_date', '-created_at']

    def __str__(self):
        return f"{self.payment_number} - {self.vendor.name}"

    def save(self, *args, **kwargs):
        if not self.payment_number:
            self.payment_number = self._generate_payment_number()
        super().save(*args, **kwargs)

    def _generate_payment_number(self):
        year = self.payment_date.year if self.payment_date else timezone.now().year
        prefix = f"PAY-{year}-"
        last_payment = Payment.objects.filter(
            organisation=self.organisation,
            payment_number__startswith=prefix
        ).order_by('-payment_number').first()

        if last_payment:
            try:
                number = int(last_payment.payment_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                number = 1
        else:
            number = 1

        return f"{prefix}{number:06d}"


class PaymentLine(models.Model):
    """Application of payment to specific bills."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(
        Payment,
        on_delete=models.CASCADE,
        related_name='applications'
    )
    bill = models.ForeignKey(
        Bill,
        on_delete=models.CASCADE,
        related_name='payments'
    )

    amount = models.DecimalField(_('Amount'), max_digits=20, decimal_places=2)

    # Discount taken
    discount_taken = models.DecimalField(_('Discount Taken'), max_digits=20, decimal_places=2, default=0)

    class Meta:
        db_table = 'payment_applications'
        verbose_name = _('Payment Application')
        verbose_name_plural = _('Payment Applications')

    def __str__(self):
        return f"{self.payment.payment_number} - {self.bill.bill_number}"
