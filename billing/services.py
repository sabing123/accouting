import stripe
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from typing import Optional

from billing.models import Plan, Subscription, PaymentHistory, Coupon
from organisations.models import Organisation


class StripeService:
    """Service for Stripe integration."""

    def __init__(self):
        stripe.api_key = settings.STRIPE_API_KEY

    @staticmethod
    def create_customer(organisation: Organisation) -> str:
        """Create a Stripe customer for an organisation."""
        customer = stripe.Customer.create(
            email=organisation.email,
            name=organisation.name,
            metadata={
                'organisation_id': str(organisation.id),
                'organisation_slug': organisation.slug,
            }
        )
        return customer.id

    @staticmethod
    def get_customer(customer_id: str) -> stripe.Customer:
        """Get a Stripe customer."""
        return stripe.Customer.retrieve(customer_id)

    @staticmethod
    def update_customer(customer_id: str, **kwargs) -> stripe.Customer:
        """Update a Stripe customer."""
        return stripe.Customer.modify(customer_id, **kwargs)

    @staticmethod
    def create_subscription(
        customer_id: str,
        price_id: str,
        trial_days: int = 0,
        coupon_code: str = None,
    ) -> stripe.Subscription:
        """Create a Stripe subscription."""
        params = {
            'customer': customer_id,
            'items': [{'price': price_id}],
            'payment_behavior': 'default_incomplete',
            'payment_settings': {'save_default_payment_method': 'on_subscription'},
            'expand': ['latest_invoice.payment_intent'],
        }

        if trial_days > 0:
            params['trial_period_days'] = trial_days

        if coupon_code:
            try:
                coupon = Coupon.objects.get(code=coupon_code, is_active=True)
                if coupon.stripe_coupon_id:
                    params['coupon'] = coupon.stripe_coupon_id
            except Coupon.DoesNotExist:
                pass

        return stripe.Subscription.create(**params)

    @staticmethod
    def cancel_subscription(subscription_id: str, immediately: bool = False) -> stripe.Subscription:
        """Cancel a Stripe subscription."""
        if immediately:
            return stripe.Subscription.delete(subscription_id)
        else:
            return stripe.Subscription.modify(
                subscription_id,
                cancel_at_period_end=True
            )

    @staticmethod
    def reactivate_subscription(subscription_id: str) -> stripe.Subscription:
        """Reactivate a cancelled subscription."""
        return stripe.Subscription.modify(
            subscription_id,
            cancel_at_period_end=False
        )

    @staticmethod
    def update_subscription_price(subscription_id: str, new_price_id: str) -> stripe.Subscription:
        """Update the price on a subscription."""
        subscription = stripe.Subscription.retrieve(subscription_id)

        return stripe.Subscription.modify(
            subscription_id,
            items=[{
                'id': subscription['items']['data'][0].id,
                'price': new_price_id,
            }],
            proration_behavior='always_invoice',
        )

    @staticmethod
    def get_payment_methods(customer_id: str) -> list:
        """Get all payment methods for a customer."""
        return stripe.PaymentMethod.list(
            customer=customer_id,
            type='card',
        ).data

    @staticmethod
    def attach_payment_method(customer_id: str, payment_method_id: str) -> stripe.PaymentMethod:
        """Attach a payment method to a customer."""
        return stripe.PaymentMethod.attach(
            payment_method_id,
            customer=customer_id,
        )

    @staticmethod
    def set_default_payment_method(customer_id: str, payment_method_id: str):
        """Set the default payment method for a customer."""
        stripe.Customer.modify(
            customer_id,
            invoice_settings={'default_payment_method': payment_method_id}
        )

    @staticmethod
    def create_invoice(customer_id: str, amount: int, description: str) -> stripe.Invoice:
        """Create a one-time invoice."""
        # Create invoice item
        stripe.InvoiceItem.create(
            customer=customer_id,
            amount=amount,
            currency='usd',
            description=description,
        )

        # Create and pay invoice
        invoice = stripe.Invoice.create(
            customer=customer_id,
            auto_advance=True,
        )

        return stripe.Invoice.pay(invoice.id)


class SubscriptionService:
    """Service for managing subscriptions."""

    @staticmethod
    @transaction.atomic
    def start_trial(organisation: Organisation, plan: Plan) -> Subscription:
        """Start a trial subscription."""
        now = timezone.now()

        subscription, created = Subscription.objects.get_or_create(
            organisation=organisation,
            defaults={
                'plan': plan,
                'status': Subscription.Status.TRIALING,
                'trial_start': now,
                'trial_end': now + timedelta(days=plan.trial_days),
                'current_period_start': now,
                'current_period_end': now + timedelta(days=plan.trial_days),
                'price': plan.price_monthly,
            }
        )

        # Update organisation subscription status
        organisation.subscription_status = Organisation.SubscriptionStatus.TRIAL
        organisation.trial_ends_at = subscription.trial_end
        organisation.save()

        return subscription

    @staticmethod
    @transaction.atomic
    def activate_subscription(
        organisation: Organisation,
        plan: Plan,
        billing_period: str = 'monthly',
        payment_method_id: str = None,
        coupon_code: str = None,
    ) -> Subscription:
        """Activate a subscription with Stripe."""

        subscription, created = Subscription.objects.get_or_create(
            organisation=organisation,
            defaults={'plan': plan}
        )

        # Create Stripe customer if needed
        if not subscription.stripe_customer_id:
            customer_id = StripeService.create_customer(organisation)
            subscription.stripe_customer_id = customer_id
            organisation.stripe_customer_id = customer_id
            organisation.save()

        # Get the appropriate price ID
        if billing_period == 'yearly':
            price_id = plan.stripe_price_yearly_id
            price = plan.price_yearly
        else:
            price_id = plan.stripe_price_monthly_id
            price = plan.price_monthly

        # Attach payment method
        if payment_method_id:
            StripeService.attach_payment_method(
                subscription.stripe_customer_id,
                payment_method_id
            )
            StripeService.set_default_payment_method(
                subscription.stripe_customer_id,
                payment_method_id
            )
            subscription.stripe_payment_method_id = payment_method_id

        # Create Stripe subscription
        stripe_sub = StripeService.create_subscription(
            customer_id=subscription.stripe_customer_id,
            price_id=price_id,
            coupon_code=coupon_code,
        )

        # Update subscription record
        subscription.stripe_subscription_id = stripe_sub.id
        subscription.status = Subscription.Status.ACTIVE
        subscription.billing_period = billing_period
        subscription.price = price
        subscription.current_period_start = timezone.datetime.fromtimestamp(stripe_sub.current_period_start, tz=timezone.utc)
        subscription.current_period_end = timezone.datetime.fromtimestamp(stripe_sub.current_period_end, tz=timezone.utc)
        subscription.save()

        # Update organisation
        organisation.subscription_status = Organisation.SubscriptionStatus.SUBSCRIBED
        organisation.subscription_plan = plan.code
        organisation.save()

        return subscription

    @staticmethod
    @transaction.atomic
    def cancel_subscription(subscription: Subscription, reason: str = '', immediately: bool = False) -> Subscription:
        """Cancel a subscription."""

        if subscription.stripe_subscription_id:
            StripeService.cancel_subscription(
                subscription.stripe_subscription_id,
                immediately=immediately
            )

        now = timezone.now()
        subscription.cancel_at_period_end = not immediately
        subscription.cancelled_at = now
        subscription.cancellation_reason = reason

        if immediately:
            subscription.status = Subscription.Status.CANCELLED
            subscription.organisation.subscription_status = Organisation.SubscriptionStatus.CANCELLED
            subscription.organisation.save()

        subscription.save()

        return subscription

    @staticmethod
    @transaction.atomic
    def reactivate_subscription(subscription: Subscription) -> Subscription:
        """Reactivate a cancelled subscription."""

        if subscription.stripe_subscription_id:
            StripeService.reactivate_subscription(subscription.stripe_subscription_id)

        subscription.cancel_at_period_end = False
        subscription.cancelled_at = None
        subscription.cancellation_reason = ''
        subscription.status = Subscription.Status.ACTIVE
        subscription.save()

        subscription.organisation.subscription_status = Organisation.SubscriptionStatus.SUBSCRIBED
        subscription.organisation.save()

        return subscription

    @staticmethod
    @transaction.atomic
    def change_plan(subscription: Subscription, new_plan: Plan) -> Subscription:
        """Change the subscription plan."""

        # Get new price ID
        if subscription.billing_period == 'yearly':
            new_price_id = new_plan.stripe_price_yearly_id
            new_price = new_plan.price_yearly
        else:
            new_price_id = new_plan.stripe_price_monthly_id
            new_price = new_plan.price_monthly

        # Update Stripe subscription
        if subscription.stripe_subscription_id:
            StripeService.update_subscription_price(
                subscription.stripe_subscription_id,
                new_price_id
            )

        subscription.plan = new_plan
        subscription.price = new_price
        subscription.save()

        return subscription

    @staticmethod
    def handle_webhook_event(event) -> bool:
        """Handle Stripe webhook events."""

        event_type = event['type']
        data = event['data']['object']

        if event_type == 'invoice.paid':
            return SubscriptionService._handle_invoice_paid(data)
        elif event_type == 'invoice.payment_failed':
            return SubscriptionService._handle_payment_failed(data)
        elif event_type == 'customer.subscription.updated':
            return SubscriptionService._handle_subscription_updated(data)
        elif event_type == 'customer.subscription.deleted':
            return SubscriptionService._handle_subscription_deleted(data)

        return True

    @staticmethod
    @transaction.atomic
    def _handle_invoice_paid(invoice_data) -> bool:
        """Handle invoice paid event."""
        customer_id = invoice_data.get('customer')
        subscription_id = invoice_data.get('subscription')

        try:
            subscription = Subscription.objects.get(stripe_subscription_id=subscription_id)
        except Subscription.DoesNotExist:
            return False

        # Record payment
        PaymentHistory.objects.create(
            organisation=subscription.organisation,
            subscription=subscription,
            stripe_invoice_id=invoice_data['id'],
            stripe_charge_id=invoice_data.get('charge'),
            amount=Decimal(str(invoice_data['amount_paid'])) / 100,
            currency=invoice_data['currency'].upper(),
            status=PaymentHistory.Status.SUCCEEDED,
            description=f"Subscription payment - {subscription.plan.name}",
            invoice_number=invoice_data.get('number', ''),
            paid_at=timezone.now(),
            metadata=invoice_data,
        )

        # Update subscription status
        subscription.status = Subscription.Status.ACTIVE
        subscription.current_period_start = timezone.datetime.fromtimestamp(
            invoice_data['period_start'], tz=timezone.utc
        )
        subscription.current_period_end = timezone.datetime.fromtimestamp(
            invoice_data['period_end'], tz=timezone.utc
        )
        subscription.save()

        return True

    @staticmethod
    @transaction.atomic
    def _handle_payment_failed(invoice_data) -> bool:
        """Handle payment failed event."""
        subscription_id = invoice_data.get('subscription')

        try:
            subscription = Subscription.objects.get(stripe_subscription_id=subscription_id)
        except Subscription.DoesNotExist:
            return False

        subscription.status = Subscription.Status.PAST_DUE
        subscription.save()

        # Record failed payment
        PaymentHistory.objects.create(
            organisation=subscription.organisation,
            subscription=subscription,
            stripe_invoice_id=invoice_data['id'],
            amount=Decimal(str(invoice_data['amount_due'])) / 100,
            currency=invoice_data['currency'].upper(),
            status=PaymentHistory.Status.FAILED,
            failure_code=invoice_data.get('last_finalization_error', {}).get('code', ''),
            failure_message=invoice_data.get('last_finalization_error', {}).get('message', ''),
            metadata=invoice_data,
        )

        return True

    @staticmethod
    @transaction.atomic
    def _handle_subscription_updated(subscription_data) -> bool:
        """Handle subscription updated event."""
        subscription_id = subscription_data.get('id')

        try:
            subscription = Subscription.objects.get(stripe_subscription_id=subscription_id)
        except Subscription.DoesNotExist:
            return False

        status_map = {
            'active': Subscription.Status.ACTIVE,
            'trialing': Subscription.Status.TRIALING,
            'past_due': Subscription.Status.PAST_DUE,
            'canceled': Subscription.Status.CANCELLED,
            'paused': Subscription.Status.PAUSED,
        }

        subscription.status = status_map.get(
            subscription_data['status'],
            Subscription.Status.ACTIVE
        )
        subscription.current_period_start = timezone.datetime.fromtimestamp(
            subscription_data['current_period_start'], tz=timezone.utc
        )
        subscription.current_period_end = timezone.datetime.fromtimestamp(
            subscription_data['current_period_end'], tz=timezone.utc
        )
        subscription.cancel_at_period_end = subscription_data.get('cancel_at_period_end', False)
        subscription.save()

        return True

    @staticmethod
    @transaction.atomic
    def _handle_subscription_deleted(subscription_data) -> bool:
        """Handle subscription deleted event."""
        subscription_id = subscription_data.get('id')

        try:
            subscription = Subscription.objects.get(stripe_subscription_id=subscription_id)
        except Subscription.DoesNotExist:
            return False

        subscription.status = Subscription.Status.CANCELLED
        subscription.save()

        subscription.organisation.subscription_status = Organisation.SubscriptionStatus.CANCELLED
        subscription.organisation.save()

        return True
