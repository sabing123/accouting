import pytest
from decimal import Decimal
from django.utils import timezone

from payables.models import Vendor, Bill, Payment, PaymentMethod
from payables.services import VendorService, BillService, PaymentService


@pytest.mark.django_db
class TestVendorService:
    """Tests for Vendor Service."""

    def test_create_vendor(self, organisation):
        """Test creating a vendor."""
        vendor = VendorService.create_vendor(
            organisation=organisation,
            name='Acme Corp',
            email='vendor@acme.com',
        )

        assert vendor.name == 'Acme Corp'
        assert vendor.email == 'vendor@acme.com'
        assert vendor.status == Vendor.Status.ACTIVE
        assert vendor.vendor_number.startswith('V-')

    def test_deactivate_vendor(self, organisation):
        """Test deactivating a vendor."""
        vendor = VendorService.create_vendor(
            organisation=organisation,
            name='Test Vendor',
            email='test@vendor.com',
        )

        VendorService.deactivate_vendor(vendor)

        vendor.refresh_from_db()
        assert vendor.status == Vendor.Status.INACTIVE
        assert vendor.is_active is False

    def test_get_vendor_statement(self, organisation, user):
        """Test getting vendor statement."""
        from ledger.services import ChartOfAccountsService

        # Setup accounts
        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        vendor = VendorService.create_vendor(
            organisation=organisation,
            name='Vendor A',
            email='a@vendor.com',
        )

        # Create a bill
        BillService.create_bill(
            organisation=organisation,
            vendor=vendor,
            bill_date=timezone.now().date(),
            due_date=timezone.now().date(),
            lines=[{
                'account': organisation.accounts.get(code='5110').id,
                'description': 'Test service',
                'quantity': 1,
                'unit_price': 500,
            }],
            created_by=user,
        )

        statement = VendorService.get_vendor_statement(vendor)

        assert 'vendor' in statement
        assert 'total_due' in statement or statement['total_due'] == 0


@pytest.mark.django_db
class TestBillService:
    """Tests for Bill Service."""

    def test_create_bill(self, organisation, user):
        """Test creating a bill."""
        from ledger.services import ChartOfAccountsService

        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        vendor = Vendor.objects.create(
            organisation=organisation,
            name='Test Vendor',
            email='test@vendor.com',
        )

        bill = BillService.create_bill(
            organisation=organisation,
            vendor=vendor,
            bill_date=timezone.now().date(),
            due_date=timezone.now().date(),
            lines=[
                {
                    'account': organisation.accounts.get(code='5110').id,
                    'description': 'Consulting services',
                    'quantity': Decimal('10'),
                    'unit_price': Decimal('100'),
                },
            ],
            created_by=user,
        )

        assert bill.vendor == vendor
        assert bill.status == Bill.Status.DRAFT
        assert bill.total == Decimal('1000')
        assert bill.balance == Decimal('1000')
        assert bill.lines.count() == 1

    def test_post_bill(self, organisation, user):
        """Test posting a bill."""
        from ledger.services import ChartOfAccountsService

        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        vendor = Vendor.objects.create(
            organisation=organisation,
            name='Test Vendor',
            email='test@vendor.com',
        )

        bill = BillService.create_bill(
            organisation=organisation,
            vendor=vendor,
            bill_date=timezone.now().date(),
            due_date=timezone.now().date(),
            lines=[{
                'account': organisation.accounts.get(code='5110').id,
                'description': 'Test',
                'quantity': 1,
                'unit_price': 500,
            }],
            created_by=user,
        )

        BillService.post_bill(bill, user)

        bill.refresh_from_db()
        assert bill.status == Bill.Status.OPEN
        assert bill.journal_entry is not None


@pytest.mark.django_db
class TestPaymentService:
    """Tests for Payment Service."""

    def test_create_payment(self, organisation, user):
        """Test creating a payment."""
        from ledger.services import ChartOfAccountsService

        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        vendor = Vendor.objects.create(
            organisation=organisation,
            name='Test Vendor',
            email='test@vendor.com',
        )

        # Create and post a bill
        bill = BillService.create_bill(
            organisation=organisation,
            vendor=vendor,
            bill_date=timezone.now().date(),
            due_date=timezone.now().date(),
            lines=[{
                'account': organisation.accounts.get(code='5110').id,
                'description': 'Test',
                'quantity': 1,
                'unit_price': 500,
            }],
            created_by=user,
        )
        BillService.post_bill(bill, user)

        # Create payment method
        payment_method = PaymentMethod.objects.create(
            organisation=organisation,
            name='Bank Transfer',
            type='ach',
        )

        payment = PaymentService.create_payment(
            organisation=organisation,
            vendor=vendor,
            payment_date=timezone.now().date(),
            amount=Decimal('500'),
            payment_method=payment_method,
            applications=[{'bill_id': bill.id, 'amount': '500'}],
            created_by=user,
        )

        assert payment.vendor == vendor
        assert payment.amount == Decimal('500')
        assert payment.status == Payment.Status.DRAFT

        # Bill should be marked as paid
        bill.refresh_from_db()
        assert bill.status == Bill.Status.PAID
        assert bill.balance == Decimal('0')
