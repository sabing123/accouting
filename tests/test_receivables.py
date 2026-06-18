import pytest
from decimal import Decimal
from django.utils import timezone

from receivables.models import Customer, Invoice, Receipt, Product
from receivables.services import CustomerService, InvoiceService, ReceiptService


@pytest.mark.django_db
class TestCustomerService:
    """Tests for Customer Service."""

    def test_create_customer(self, organisation):
        """Test creating a customer."""
        customer = CustomerService.create_customer(
            organisation=organisation,
            name='Customer A',
            email='customer@example.com',
        )

        assert customer.name == 'Customer A'
        assert customer.email == 'customer@example.com'
        assert customer.status == Customer.Status.ACTIVE
        assert customer.customer_number.startswith('C-')

    def test_deactivate_customer(self, organisation):
        """Test deactivating a customer."""
        customer = CustomerService.create_customer(
            organisation=organisation,
            name='Test Customer',
            email='test@customer.com',
        )

        CustomerService.deactivate_customer(customer)

        customer.refresh_from_db()
        assert customer.status == Customer.Status.INACTIVE
        assert customer.is_active is False


@pytest.mark.django_db
class TestInvoiceService:
    """Tests for Invoice Service."""

    def test_create_invoice(self, organisation, user):
        """Test creating an invoice."""
        from ledger.services import ChartOfAccountsService

        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        customer = Customer.objects.create(
            organisation=organisation,
            name='Test Customer',
            email='test@customer.com',
        )

        invoice = InvoiceService.create_invoice(
            organisation=organisation,
            customer=customer,
            invoice_date=timezone.now().date(),
            lines=[{
                'account': organisation.accounts.get(code='4100').id,
                'description': 'Consulting services',
                'quantity': Decimal('10'),
                'unit_price': Decimal('100'),
            }],
            created_by=user,
        )

        assert invoice.customer == customer
        assert invoice.status == Invoice.Status.DRAFT
        assert invoice.total == Decimal('1000')
        assert invoice.balance == Decimal('1000')
        assert invoice.lines.count() == 1

    def test_send_invoice(self, organisation, user):
        """Test sending an invoice."""
        from ledger.services import ChartOfAccountsService

        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        customer = Customer.objects.create(
            organisation=organisation,
            name='Test Customer',
            email='test@customer.com',
        )

        invoice = InvoiceService.create_invoice(
            organisation=organisation,
            customer=customer,
            invoice_date=timezone.now().date(),
            lines=[{
                'account': organisation.accounts.get(code='4100').id,
                'description': 'Test',
                'quantity': 1,
                'unit_price': 500,
            }],
            created_by=user,
        )

        InvoiceService.send_invoice(invoice, user)

        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.SENT
        assert invoice.journal_entry is not None

    def test_cancel_invoice(self, organisation, user):
        """Test cancelling an invoice."""
        from ledger.services import ChartOfAccountsService

        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        customer = Customer.objects.create(
            organisation=organisation,
            name='Test Customer',
            email='test@customer.com',
        )

        invoice = InvoiceService.create_invoice(
            organisation=organisation,
            customer=customer,
            invoice_date=timezone.now().date(),
            lines=[{
                'account': organisation.accounts.get(code='4100').id,
                'description': 'Test',
                'quantity': 1,
                'unit_price': 500,
            }],
            created_by=user,
        )

        InvoiceService.send_invoice(invoice, user)
        InvoiceService.cancel_invoice(invoice, user, 'Test cancellation')

        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.CANCELLED


@pytest.mark.django_db
class TestReceiptService:
    """Tests for Receipt Service."""

    def test_create_receipt(self, organisation, user):
        """Test creating a receipt."""
        from ledger.services import ChartOfAccountsService

        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        customer = Customer.objects.create(
            organisation=organisation,
            name='Test Customer',
            email='test@customer.com',
        )

        invoice = InvoiceService.create_invoice(
            organisation=organisation,
            customer=customer,
            invoice_date=timezone.now().date(),
            lines=[{
                'account': organisation.accounts.get(code='4100').id,
                'description': 'Test',
                'quantity': 1,
                'unit_price': 500,
            }],
            created_by=user,
        )
        InvoiceService.send_invoice(invoice, user)

        receipt = ReceiptService.create_receipt(
            organisation=organisation,
            customer=customer,
            receipt_date=timezone.now().date(),
            amount=Decimal('500'),
            applications=[{'invoice_id': invoice.id, 'amount': '500'}],
            created_by=user,
        )

        assert receipt.customer == customer
        assert receipt.amount == Decimal('500')
        assert receipt.status == Receipt.Status.DRAFT

        # Invoice should be marked as paid
        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.PAID


@pytest.mark.django_db
class TestProductModel:
    """Tests for Product model."""

    def test_create_product(self, organisation):
        """Test creating a product."""
        from ledger.services import ChartOfAccountsService

        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        product = Product.objects.create(
            organisation=organisation,
            name='Consulting Service',
            type=Product.Type.SERVICE,
            unit_price=Decimal('150'),
            unit='Hour',
            revenue_account=organisation.accounts.get(code='4100'),
        )

        assert product.name == 'Consulting Service'
        assert product.product_code.startswith('PROD-')
        assert product.unit_price == Decimal('150')
