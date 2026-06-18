from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from organisations.models import Organisation
from decimal import Decimal
import uuid


class PlanManager(models.Manager):
    """Manager for Subscription Plan model."""

    def get_queryset(self):
        return super().get_queryset()

    def active(self):
        return self.get_queryset().filter(is_active=True)


class Plan(models.Model):
    """Subscription plans for the SaaS platform."""

    class BillingPeriod(models.TextChoices):
        MONTHLY = 'monthly', _('Monthly')
        QUARTERLY = 'quarterly', _('Quarterly')
        YEARLY = 'yearly', _('Yearly')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(_('Plan Name'), max_length=100)
    code = models.CharField(_('Plan Code'), max_length=50, unique=True)
    description = models.TextField(_('Description'), blank=True)

    # Pricing
    price_monthly = models.DecimalField(_('Monthly Price'), max_digits=10, decimal_places=2, default=0)
    price_yearly = models.DecimalField(_('Yearly Price'), max_digits=10, decimal_places=2, default=0)

    # Stripe
    stripe_price_monthly_id = models.CharField(_('Stripe Monthly Price ID'), max_length=100, blank=True)
    stripe_price_yearly_id = models.CharField(_('Stripe Yearly Price ID'), max_length=100, blank=True)

    # Features/limits
    features = models.JSONField(_('Features'), default=dict, blank=True)
    max_users = models.IntegerField(_('Max Users'), default=5)
    max_customers = models.IntegerField(_('Max Customers'), default=100)
    max_vendors = models.IntegerField(_('Max Vendors'), default=100)
    max_invoices_monthly = models.IntegerField(_('Max Invoices/Month'), default=100)

    # Status
    is_active = models.BooleanField(_('Is Active'), default=True)
    is_default = models.BooleanField(_('Is Default'), default=False)
    trial_days = models.IntegerField(_('Trial Days'), default=14)

    # Ordering
    sort_order = models.IntegerField(_('Sort Order'), default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PlanManager()

    class Meta:
        db_table = 'billing_plans'
        verbose_name = _('Subscription Plan')
        verbose_name_plural = _('Subscription Plans')
        ordering = ['sort_order', 'price_monthly']

    def __str__(self):
        return self.name

    @property
    def display_price(self):
        """Return formatted price display."""
        return f"${self.price_monthly}/month" if self.price_monthly > 0 else "Free"


class Subscription(models.Model):
    """Subscription for an organisation."""

    class Status(models.TextChoices):
        TRIALING = 'trialing', _('Trialing')
        ACTIVE = 'active', _('Active')
        PAST_DUE = 'past_due', _('Past Due')
        CANCELLED = 'cancelled', _('Cancelled')
        EXPIRED = 'expired', _('Expired')
        PAUSED = 'paused', _('Paused')

    class BillingPeriod(models.TextChoices):
        MONTHLY = 'monthly', _('Monthly')
        QUARTERLY = 'quarterly', _('Quarterly')
        YEARLY = 'yearly', _('Yearly')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.OneToOneField(
        Organisation,
        on_delete=models.CASCADE,
        related_name='subscription'
    )
    plan = models.ForeignKey(
        Plan,
        on_delete=models.SET_NULL,
        null=True,
        related_name='subscriptions'
    )

    # Status
    status = models.CharField(_('Status'), max_length=20, choices=Status.choices, default=Status.TRIALING)

    # Billing period
    billing_period = models.CharField(_('Billing Period'), max_length=20, choices=BillingPeriod.choices, default=BillingPeriod.MONTHLY)

    # Stripe
    stripe_customer_id = models.CharField(_('Stripe Customer ID'), max_length=100, blank=True)
    stripe_subscription_id = models.CharField(_('Stripe Subscription ID'), max_length=100, blank='True')
    stripe_payment_method_id = models.CharField(_('Stripe Payment Method ID'), max_length=100, blank=True)

    # Dates
    trial_start = models.DateTimeField(_('Trial Start'), null=True, blank=True)
    trial_end = models.DateTimeField(_('Trial End'), null=True, blank=True)
    current_period_start = models.DateTimeField(_('Current Period Start'), null=True, blank=True)
    current_period_end = models.DateTimeField(_('Current Period End'), null=True, blank=True)

    # Cancellation
    cancel_at_period_end = models.BooleanField(_('Cancel at Period End'), default=False)
    cancelled_at = models.DateTimeField(_('Cancelled At'), null=True, blank=True)
    cancellation_reason = models.TextField(_('Cancellation Reason'), blank=True)

    # Pricing (for historical accuracy)
    price = models.DecimalField(_('Price'), max_digits=10, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'billing_subscriptions'
        verbose_name = _('Subscription')
        verbose_name_plural = _('Subscriptions')

    def __str__(self):
        return f"{self.organisation.name} - {self.plan.name if self.plan else 'No Plan'}"

    @property
    def is_trial(self):
        from django.utils import timezone
        return self.status == self.Status.TRIALING and self.trial_end and self.trial_end > timezone.now()

    @property
    def is_active(self):
        return self.status in [self.Status.ACTIVE, self.Status.TRIALING, self.Status.PAST_DUE]

    @property
    def days_until_renewal(self):
        from django.utils import timezone
        if self.current_period_end:
            delta = self.current_period_end - timezone.now()
            return delta.days if delta.days > 0 else 0
        return None

    def get_feature_limit(self, feature_name: str) -> int:
        """Get the limit for a specific feature."""
        if self.plan:
            return getattr(self.plan, feature_name, None) or self.plan.features.get(feature_name)
        return None


class PaymentHistory(models.Model):
    """Record of all payments made through Stripe."""

    class Status(models.TextChoices):
        SUCCEEDED = 'succeeded', _('Succeeded')
        PENDING = 'pending', _('Pending')
        FAILED = 'failed', _('Failed')
        REFUNDED = 'refunded', _('Refunded')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='payment_history'
    )
    subscription = models.ForeignKey(
        Subscription,
        on_delete=models.SET_NULL,
        null=True,
        related_name='payments'
    )

    # Stripe references
    stripe_invoice_id = models.CharField(_('Stripe Invoice ID'), max_length=100, blank=True)
    stripe_charge_id = models.CharField(_('Stripe Charge ID'), max_length=100, blank=True)
    stripe_payment_intent_id = models.CharField(_('Stripe Payment Intent ID'), max_length=100, blank=True)

    # Amount
    amount = models.DecimalField(_('Amount'), max_digits=10, decimal_places=2)
    currency = models.CharField(_('Currency'), max_length=3, default='USD')
    amount_refunded = models.DecimalField(_('Amount Refunded'), max_digits=10, decimal_places=2, default=0)

    # Status
    status = models.CharField(_('Status'), max_length=20, choices=Status.choices, default=Status.PENDING)

    # Description
    description = models.CharField(_('Description'), max_length=255, blank=True)
    invoice_number = models.CharField(_('Invoice Number'), max_length=50, blank=True)

    # Dates
    paid_at = models.DateTimeField(_('Paid At'), null=True, blank=True)
    refunded_at = models.DateTimeField(_('Refunded At'), null=True, blank=True)

    # Failure
    failure_code = models.CharField(_('Failure Code'), max_length=50, blank=True)
    failure_message = models.TextField(_('Failure Message'), blank=True)

    # Metadata
    metadata = models.JSONField(_('Metadata'), default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'billing_payment_history'
        verbose_name = _('Payment History')
        verbose_name_plural = _('Payment History')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.organisation.name} - ${self.amount} - {self.status}"


class Coupon(models.Model):
    """Discount coupons for subscriptions."""

    class Type(models.TextChoices):
        PERCENTAGE = 'percentage', _('Percentage')
        FIXED_AMOUNT = 'fixed', _('Fixed Amount')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    code = models.CharField(_('Coupon Code'), max_length=50, unique=True)
    description = models.CharField(_('Description'), max_length=255, blank=True)

    discount_type = models.CharField(_('Discount Type'), max_length=20, choices=Type.choices)
    discount_value = models.DecimalField(_('Discount Value'), max_digits=10, decimal_places=2)

    # Limits
    max_redemptions = models.IntegerField(_('Max Redemptions'), default=0, help_text=_('0 for unlimited'))
    redemptions_count = models.IntegerField(_('Redemptions Count'), default=0)

    # Duration
    duration_months = models.IntegerField(_('Duration (Months)'), default=1, help_text=_('How many billing cycles the coupon applies'))

    # Validity
    valid_from = models.DateTimeField(_('Valid From'), null=True, blank=True)
    valid_until = models.DateTimeField(_('Valid Until'), null=True, blank=True)
    is_active = models.BooleanField(_('Is Active'), default=True)

    # Stripe
    stripe_coupon_id = models.CharField(_('Stripe Coupon ID'), max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'billing_coupons'
        verbose_name = _('Coupon')
        verbose_name_plural = _('Coupons')

    def __str__(self):
        return self.code

    @property
    def is_valid(self):
        from django.utils import timezone
        now = timezone.now()

        if not self.is_active:
            return False

        if self.valid_from and now < self.valid_from:
            return False

        if self.valid_until and now > self.valid_until:
            return False

        if self.max_redemptions > 0 and self.redemptions_count >= self.max_redemptions:
            return False

        return True

    def apply(self, amount: Decimal) -> Decimal:
        """Apply the coupon to an amount."""
        if self.discount_type == self.Type.PERCENTAGE:
            return amount * (self.discount_value / 100)
        else:
            return min(amount, self.discount_value)
