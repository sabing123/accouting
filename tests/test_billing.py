import pytest
from django.utils import timezone
from unittest.mock import Mock, patch, MagicMock

from billing.models import Plan, Subscription, PaymentHistory
from billing.services import StripeService, SubscriptionService
from organisations.models import Organisation


@pytest.fixture
def plan():
    """Create a test subscription plan."""
    return Plan.objects.create(
        name='Basic Plan',
        code='basic-monthly',
        price_monthly=29.99,
        price_yearly=299.99,
        stripe_price_monthly_id='price_test_monthly',
        stripe_price_yearly_id='price_test_yearly',
        max_users=5,
        is_active=True,
    )


@pytest.mark.django_db
class TestStripeService:
    """Tests for Stripe Service."""

    @patch('stripe.Customer.create')
    def test_create_customer(self, mock_create, organisation):
        """Test creating a Stripe customer."""
        mock_create.return_value = Mock(id='cus_test123')

        customer_id = StripeService.create_customer(organisation)

        assert customer_id == 'cus_test123'
        mock_create.assert_called_once()

    @patch('stripe.Subscription.create')
    def test_create_subscription(self, mock_create):
        """Test creating a Stripe subscription."""
        mock_sub = MagicMock()
        mock_sub.id = 'sub_test123'
        mock_sub.status = 'active'
        mock_create.return_value = mock_sub

        subscription = StripeService.create_subscription(
            customer_id='cus_test123',
            price_id='price_test',
            trial_days=14,
        )

        assert subscription.id == 'sub_test123'
        mock_create.assert_called_once()


@pytest.mark.django_db
class TestSubscriptionService:
    """Tests for Subscription Service."""

    def test_start_trial(self, organisation, plan):
        """Test starting a trial subscription."""
        subscription = SubscriptionService.start_trial(organisation, plan)

        assert subscription.status == Subscription.Status.TRIALING
        assert subscription.plan == plan
        assert subscription.trial_end is not None

        organisation.refresh_from_db()
        assert organisation.subscription_status == Organisation.SubscriptionStatus.TRIAL

    @patch.object(StripeService, 'create_customer')
    @patch.object(StripeService, 'create_subscription')
    def test_activate_subscription(self, mock_stripe_create, mock_customer_create, organisation, plan, user):
        """Test activating a subscription."""
        mock_customer_create.return_value = 'cus_test123'
        mock_stripe_sub = MagicMock()
        mock_stripe_sub.id = 'sub_test123'
        mock_stripe_sub.current_period_start = timezone.now().timestamp()
        mock_stripe_sub.current_period_end = timezone.now().timestamp() + 2592000  # +30 days
        mock_stripe_create.return_value = mock_stripe_create

        # Start trial first
        SubscriptionService.start_trial(organisation, plan)

        # Activate
        subscription = SubscriptionService.activate_subscription(
            organisation=organisation,
            plan=plan,
            billing_period='monthly',
            payment_method_id='pm_test123',
        )

        assert subscription.status == Subscription.Status.ACTIVE
        assert subscription.stripe_customer_id == 'cus_test123'

        organisation.refresh_from_db()
        assert organisation.subscription_status == Organisation.SubscriptionStatus.SUBSCRIBED

    def test_cancel_subscription(self, organisation, plan, user):
        """Test cancelling a subscription."""
        # Start subscription
        subscription = SubscriptionService.start_trial(organisation, plan)
        subscription.status = Subscription.Status.ACTIVE
        subscription.save()

        # Cancel
        SubscriptionService.cancel_subscription(subscription, 'No longer needed')

        subscription.refresh_from_db()
        assert subscription.cancel_at_period_end is True
        assert subscription.cancelled_at is not None


@pytest.mark.django_db
class TestPlanModel:
    """Tests for Plan model."""

    def test_plan_creation(self, plan):
        """Test plan is created correctly."""
        assert plan.name == 'Basic Plan'
        assert plan.price_monthly == Decimal('29.99')
        assert plan.is_active is True

    def test_display_price(self, plan):
        """Test display price property."""
        assert plan.display_price == "$29.99/month"

    def test_free_plan_display_price(self):
        """Test display price for free plan."""
        free_plan = Plan.objects.create(
            name='Free Plan',
            code='free',
            price_monthly=0,
            is_active=True,
        )
        assert free_plan.display_price == "Free"
