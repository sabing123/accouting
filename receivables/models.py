from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from organisations.models import Organisation
from django.utils import timezone
import uuid


class CustomerManager(models.Manager):
    """Manager for Customer model."""

    def get_queryset(self):
        return super().get_queryset()

    def active(self):
        return self.get_queryset().filter(is_active=True)

    def with_outstanding_balance(self):
        """Get customers with outstanding invoices."""
        return self.get_queryset().filter(
            invoices__status__in=['sent', 'partial'],
            invoices__balance__gt=0
        ).distinct()


class Customer(models.Model):
    """
    Customer model for tracking accounts receivable.
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
        related_name='customers'
    )

    # Basic info
    customer_number = models.CharField(_('Customer Number'), max_length=50, blank=True)
    name = models.CharField(_('Name'), max_length=255)
    display_name = models.CharField(_('Display Name'), max_length=255, blank=True)
    contact_name = models.CharField(_('Contact Name'), max_length=255, blank=True)
    email = models.EmailField(_('Email'), blank=True)
    phone = models.CharField(_('Phone'), max_length=50, blank=True)
    mobile = models.CharField(_('Mobile'), max_length=50, blank=True)
    website = models.URLField(_('Website'), blank=True)

    # Billing address
    billing_address_line1 = models.CharField(_('Address Line 1'), max_length=255, blank=True)
    billing_address_line2 = models.CharField(_('Address Line 2'), max_length=255, blank=True)
    billing_city = models.CharField(_('City'), max_length=100, blank=True)
    billing_state_province = models.CharField(_('State/Province'), max_length=100, blank=True)
    billing_postal_code = models.CharField(_('Postal Code'), max_length=20, blank=True)
    billing_country = models.CharField(_('Country'), max_length=100, blank=True)

    # Shipping address
    shipping_address_line1 = models.CharField(_('Address Line 1'), max_length=255, blank=True)
    shipping_address_line2 = models.CharField(_('Address Line 2'), max_length=255, blank=True)
    shipping_city = models.CharField(_('City'), max_length=100, blank=True)
    shipping_state_province = models.CharField(_('State/Province'), max_length=100, blank=True)
    shipping_postal_code = models.CharField(_('Postal Code'), max_length=20, blank=True)
    shipping_country = models.CharField(_('Country'), max_length=100, blank=True)
    same_as_billing = models.BooleanField(_('Same as Billing'), default=True)

    # Tax & Payment
    tax_id = models.CharField(_('Tax ID'), max_length=50, blank=True)
    tax_code = models.CharField(_('Tax Code'), max_length=50, blank=True)
    tax_exempt = models.BooleanField(_('Tax Exempt'), default=False)
    payment_terms = models.CharField(
        _('Payment Terms'),
        max_length=20,
        choices=PaymentTerms.choices,
        default=PaymentTerms.NET_30
    )

    # Accounting defaults
    receivable_account = models.ForeignKey(
        'ledger.Account',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customers_default_receivable'
    )
    revenue_account = models.ForeignKey(
        'ledger.Account',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='customers_default_revenue'
    )

    # Status
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.ACTIVE)
    is_active = models.BooleanField(_('Is Active'), default=True)
    hold_reason = models.TextField(_('Hold Reason'), blank=True)

    # Credit limit
    credit_limit = models.DecimalField(_('Credit Limit'), max_digits=20, decimal_places=2, default=0)

    # Currency
    currency = models.CharField(_('Currency'), max_length=3, default='USD')

    # Notes
    notes = models.TextField(_('Notes'), blank=True)

    # Metadata
    custom_fields = models.JSONField(_('Custom Fields'), default=dict, blank=True)
    tags = models.JSONField(_('Tags'), default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomerManager()

    class Meta:
        db_table = 'customers'
        verbose_name = _('Customer')
        verbose_name_plural = _('Customers')
        ordering = ['name']

    def __str__(self):
        return self.display_name or self.name

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.name

        if not self.customer_number:
            self.customer_number = self._generate_customer_number()

        # Copy billing to shipping if same_as_billing
        if self.same_as_billing:
            self.shipping_address_line1 = self.billing_address_line1
            self.shipping_address_line2 = self.billing_address_line2
            self.shipping_city = self.billing_city
            self.shipping_state_province = self.billing_state_province
            self.shipping_postal_code = self.billing_postal_code
            self.shipping_country = self.billing_country

        super().save(*args, **kwargs)

    def _generate_customer_number(self):
        prefix = "C-"
        count = Customer.objects.filter(organisation=self.organisation).count()
        return f"{prefix}{count + 1:05d}"

    @property
    def outstanding_balance(self):
        """Calculate outstanding balance from open invoices."""
        return self.invoices.filter(
            status__in=['sent', 'partial']
        ).aggregate(total=models.Sum('balance'))['total'] or 0

    @property
    def available_credit(self):
        """Calculate available credit."""
        return max(0, self.credit_limit - self.outstanding_balance)


class Product(models.Model):
    """Products and services for invoicing."""

    class Type(models.TextChoices):
        PRODUCT = 'product', _('Product')
        SERVICE = 'service', _('Service')
        OTHER = 'other', _('Other')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='products'
    )

    product_code = models.CharField(_('Product Code'), max_length=50, blank=True)
    name = models.CharField(_('Name'), max_length=255)
    description = models.TextField(_('Description'), blank=True)
    type = models.CharField(_('Type'), max_length=10, choices=Type.choices, default=Type.SERVICE)

    # Pricing
    unit_price = models.DecimalField(_('Unit Price'), max_digits=20, decimal_places=2, default=0)
    unit = models.CharField(_('Unit'), max_length=20, default='Each')

    # Accounts
    revenue_account = models.ForeignKey(
        'ledger.Account',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products'
    )
    cost_account = models.ForeignKey(
        'ledger.Account',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='product_costs'
    )

    # Tax
    tax_code = models.CharField(_('Tax Code'), max_length=50, blank=True)
    tax_rate = models.DecimalField(_('Tax Rate'), max_digits=5, decimal_places=2, default=0)

    is_active = models.BooleanField(_('Is Active'), default=True)
    is_taxable = models.BooleanField(_('Is Taxable'), default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'products'
        verbose_name = _('Product/Service')
        verbose_name_plural = _('Products/Services')
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.product_code:
            count = Product.objects.filter(organisation=self.organisation).count()
            self.product_code = f"PROD-{count + 1:05d}"
        super().save(*args, **kwargs)


class InvoiceManager(models.Manager):
    """Manager for Invoice model."""

    def get_queryset(self):
        return super().get_queryset()

    def open(self):
        return self.get_queryset().filter(status='sent')

    def overdue(self):
        return self.get_queryset().filter(
            status__in=['sent', 'partial'],
            due_date__lt=timezone.now().date()
        )


class Invoice(models.Model):
    """
    Customer Invoice for accounts receivable tracking.
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PENDING = 'pending', _('Pending Approval')
        SENT = 'sent', _('Sent')
        PARTIAL = 'partial', _('Partially Paid')
        PAID = 'paid', _('Paid')
        CANCELLED = 'cancelled', _('Cancelled')

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
        related_name='invoices'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='invoices',
        verbose_name=_('Customer')
    )

    # Invoice details
    invoice_number = models.CharField(_('Invoice Number'), max_length=50, blank=True)
    quote_number = models.CharField(_('Quote Number'), max_length=50, blank=True)

    # Dates
    invoice_date = models.DateField(_('Invoice Date'), db_index=True)
    due_date = models.DateField(_('Due Date'))
    sent_date = models.DateField(_('Sent Date'), null=True, blank=True)

    # Payment terms
    payment_terms = models.CharField(
        _('Payment Terms'),
        max_length=20,
        choices=PaymentTerms.choices,
        default=PaymentTerms.NET_30
    )

    # Currency
    currency = models.CharField(_('Currency'), max_length=3, default='USD')
    exchange_rate = models.DecimalField(_('Exchange Rate'), max_digits=12, decimal_places=6, default=1)

    # Status
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.DRAFT)

    # Description
    description = models.TextField(_('Description'), blank=True)
    notes = models.TextField(_('Notes'), blank=True)
    customer_notes = models.TextField(_('Customer Notes'), blank=True)

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
        related_name='invoices'
    )

    # Department/Project
    department = models.ForeignKey(
        'organisations.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    project = models.CharField(_('Project'), max_length=100, blank=True)

    # Recurring
    recurring_invoice = models.ForeignKey(
        'RecurringInvoice',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_invoices'
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_invoices'
    )

    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='voided_invoices'
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(_('Void Reason'), blank=True)

    # Attachments
    attachments = models.JSONField(_('Attachments'), default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = InvoiceManager()

    class Meta:
        db_table = 'invoices'
        verbose_name = _('Invoice')
        verbose_name_plural = _('Invoices')
        ordering = ['-invoice_date', '-created_at']

    def __str__(self):
        return f"{self.invoice_number} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()

        # Calculate total
        self.total = self.subtotal + self.tax_amount - self.discount_amount + self.adjustment

        if self.pk is None:
            self.balance = self.total

        super().save(*args, **kwargs)

    def _generate_invoice_number(self):
        year = self.invoice_date.year if self.invoice_date else timezone.now().year
        prefix = f"INV-{year}-"
        last_invoice = Invoice.objects.filter(
            organisation=self.organisation,
            invoice_number__startswith=prefix
        ).order_by('-invoice_number').first()

        if last_invoice:
            try:
                number = int(last_invoice.invoice_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                number = 1
        else:
            number = 1

        return f"{prefix}{number:06d}"

    @property
    def is_overdue(self):
        return self.status in ['sent', 'partial'] and self.due_date < timezone.now().date()

    @property
    def days_overdue(self):
        if not self.is_overdue:
            return 0
        return (timezone.now().date() - self.due_date).days

    def calculate_due_date(self):
        """Calculate due date based on payment terms."""
        from dateutil.relativedelta import relativedelta

        if self.payment_terms == 'due_on_receipt':
            return self.invoice_date
        elif self.payment_terms == 'net_15':
            return self.invoice_date + relativedelta(days=15)
        elif self.payment_terms == 'net_30':
            return self.invoice_date + relativedelta(days=30)
        elif self.payment_terms == 'net_45':
            return self.invoice_date + relativedelta(days=45)
        elif self.payment_terms == 'net_60':
            return self.invoice_date + relativedelta(days=60)
        elif self.payment_terms == 'end_of_month':
            next_month = self.invoice_date + relativedelta(months=1)
            return next_month.replace(day=1) - relativedelta(days=1)
        return self.invoice_date


class InvoiceLine(models.Model):
    """Line items in a customer invoice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='lines'
    )

    # Item details
    description = models.CharField(_('Description'), max_length=500)
    quantity = models.DecimalField(_('Quantity'), max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(_('Unit Price'), max_digits=20, decimal_places=2)

    # Product reference
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoice_lines'
    )

    # Account
    account = models.ForeignKey(
        'ledger.Account',
        on_delete=models.PROTECT,
        related_name='invoice_lines'
    )

    # Tax
    tax_code = models.CharField(_('Tax Code'), max_length=50, blank=True)
    tax_rate = models.DecimalField(_('Tax Rate'), max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(_('Tax Amount'), max_digits=20, decimal_places=2, default=0)

    # Discount
    discount_percent = models.DecimalField(_('Discount %'), max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(_('Discount Amount'), max_digits=20, decimal_places=2, default=0)

    # Subtotal
    line_total = models.DecimalField(_('Line Total'), max_digits=20, decimal_places=2, default=0)

    # Department/Project
    department = models.ForeignKey(
        'organisations.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    sequence = models.IntegerField(_('Sequence'), default=0)

    class Meta:
        db_table = 'invoice_lines'
        verbose_name = _('Invoice Line')
        verbose_name_plural = _('Invoice Lines')
        ordering = ['sequence']

    def save(self, *args, **kwargs):
        base_total = self.quantity * self.unit_price
        self.discount_amount = base_total * (self.discount_percent / 100)
        self.line_total = base_total - self.discount_amount
        self.tax_amount = self.line_total * (self.tax_rate / 100)
        super().save(*args, **kwargs)


class RecurringInvoice(models.Model):
    """Template for recurring customer invoices."""

    class Frequency(models.TextChoices):
        WEEKLY = 'weekly', _('Weekly')
        MONTHLY = 'monthly', _('Monthly')
        QUARTERLY = 'quarterly', _('Quarterly')
        YEARLY = 'yearly', _('Yearly')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='recurring_invoices'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='recurring_invoices'
    )

    name = models.CharField(_('Name'), max_length=255)
    description = models.TextField(_('Description'), blank=True)

    frequency = models.CharField(_('Frequency'), max_length=10, choices=Frequency.choices)
    day_of_month = models.IntegerField(_('Day of Month'), default=1)

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
        db_table = 'recurring_invoices'
        verbose_name = _('Recurring Invoice')
        verbose_name_plural = _('Recurring Invoices')

    def __str__(self):
        return self.name


class Receipt(models.Model):
    """
    Payment receipt from customer for accounts receivable.
    """

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        DEPOSITED = 'deposited', _('Deposited')
        PROCESSED = 'processed', _('Processed')
        VOIDED = 'voided', _('Voided')

    class PaymentMethod(models.TextChoices):
        CHECK = 'check', _('Check')
        CASH = 'cash', _('Cash')
        CREDIT_CARD = 'credit_card', _('Credit Card')
        ACH = 'ach', _('ACH Transfer')
        WIRE = 'wire', _('Wire Transfer')
        OTHER = 'other', _('Other')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='receipts'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='receipts',
        verbose_name=_('Customer')
    )

    # Receipt details
    receipt_number = models.CharField(_('Receipt Number'), max_length=50, blank=True)
    receipt_date = models.DateField(_('Receipt Date'), db_index=True)
    payment_method = models.CharField(
        _('Payment Method'),
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CHECK
    )

    # Amount
    amount = models.DecimalField(_('Amount'), max_digits=20, decimal_places=2)
    currency = models.CharField(_('Currency'), max_length=3, default='USD')

    # Status
    status = models.CharField(_('Status'), max_length=10, choices=Status.choices, default=Status.DRAFT)

    # Check details
    check_number = models.CharField(_('Check Number'), max_length=50, blank=True)

    # Bank deposit
    bank_account = models.ForeignKey(
        'banking.BankAccount',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_('Bank Account')
    )
    deposit_date = models.DateField(_('Deposit Date'), null=True, blank=True)
    deposit_reference = models.CharField(_('Deposit Reference'), max_length=50, blank=True)

    # Reference
    reference = models.CharField(_('Reference'), max_length=100, blank=True)
    memo = models.TextField(_('Memo'), blank=True)

    # Accounting
    journal_entry = models.ForeignKey(
        'ledger.JournalEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='receipts'
    )

    # Audit
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_receipts'
    )
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_receipts'
    )
    processed_at = models.DateTimeField(null=True, blank=True)

    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='voided_receipts'
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(_('Void Reason'), blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'receipts'
        verbose_name = _('Receipt')
        verbose_name_plural = _('Receipts')
        ordering = ['-receipt_date', '-created_at']

    def __str__(self):
        return f"{self.receipt_number} - {self.customer.name}"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = self._generate_receipt_number()
        super().save(*args, **kwargs)

    def _generate_receipt_number(self):
        year = self.receipt_date.year if self.receipt_date else timezone.now().year
        prefix = f"REC-{year}-"
        last_receipt = Receipt.objects.filter(
            organisation=self.organisation,
            receipt_number__startswith=prefix
        ).order_by('-receipt_number').first()

        if last_receipt:
            try:
                number = int(last_receipt.receipt_number.split('-')[-1]) + 1
            except (ValueError, IndexError):
                number = 1
        else:
            number = 1

        return f"{prefix}{number:06d}"


class ReceiptLine(models.Model):
    """Application of receipt to specific invoices."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    receipt = models.ForeignKey(
        Receipt,
        on_delete=models.CASCADE,
        related_name='applications'
    )
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='payments'
    )

    amount = models.DecimalField(_('Amount'), max_digits=20, decimal_places=2)

    # Discount taken
    discount_taken = models.DecimalField(_('Discount Taken'), max_digits=20, decimal_places=2, default=0)

    class Meta:
        db_table = 'receipt_applications'
        verbose_name = _('Receipt Application')
        verbose_name_plural = _('Receipt Applications')

    def __str__(self):
        return f"{self.receipt.receipt_number} - {self.invoice.invoice_number}"


class CreditMemo(models.Model):
    """Credit memo for customer refunds/adjustments."""

    class Status(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        ISSUED = 'issued', _('Issued')
        APPLIED = 'applied', _('Applied')
        VOIDED = 'voided', _('Voided')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='credit_memos'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='credit_memos'
    )

    credit_number = models.CharField(_('Credit Number'), max_length=50, blank=True)
    credit_date = models.DateField(_('Credit Date'))
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='credit_memos'
    )

    amount = models.DecimalField(_('Amount'), max_digits=20, decimal_places=2)
    reason = models.TextField(_('Reason'))
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
        null=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'credit_memos'
        verbose_name = _('Credit Memo')
        verbose_name_plural = _('Credit Memos')

    def save(self, *args, **kwargs):
        if not self.credit_number:
            year = self.credit_date.year if self.credit_date else timezone.now().year
            count = CreditMemo.objects.filter(organisation=self.organisation).count()
            self.credit_number = f"CRED-{year}-{count + 1:06d}"
        super().save(*args, **kwargs)
