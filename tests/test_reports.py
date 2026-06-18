import pytest
from decimal import Decimal

from reports.services import (
    TrialBalanceService, BalanceSheetService,
    IncomeStatementService, AgedReceivablesService, AgedPayablesService
)
from ledger.services import ChartOfAccountsService
from payables.models import Vendor
from payables.services import BillService
from receivables.models import Customer
from receivables.services import InvoiceService
from dashboard.services import DashboardService


@pytest.fixture(autouse=True)
def setup_accounts(organisation, user):
    """Setup accounts for all report tests."""
    ChartOfAccountsService.setup_default_chart_of_accounts(organisation)


@pytest.mark.django_db
class TestTrialBalanceService:
    """Tests for Trial Balance Service."""

    def test_generate_trial_balance(self, organisation, user):
        """Test generating a trial balance."""
        from django.utils import timezone
        from ledger.services import JournalEntryService

        # Create transactions
        cash = organisation.accounts.get(code='1000')
        revenue = organisation.accounts.get(code='4100')

        entry = JournalEntryService.create_entry(
            organisation=organisation,
            date=timezone.now().date(),
            description='Test entry',
            lines=[
                {'account': cash.id, 'debit': 1000, 'credit': 0},
                {'account': revenue.id, 'debit': 0, 'credit': 1000},
            ],
            created_by=user,
        )
        JournalEntryService.post_entry(entry, user)

        # Generate trial balance
        tb = TrialBalanceService.generate(organisation)

        assert 'as_of' in tb
        assert 'accounts' in tb or 'grouped' in tb
        # Should be balanced
        if 'total_debits' in tb:
            assert abs(tb['total_debits'] - tb['total_credits']) < Decimal('0.01')


@pytest.mark.django_db
class TestBalanceSheetService:
    """Tests for Balance Sheet Service."""

    def test_generate_balance_sheet(self, organisation):
        """Test generating a balance sheet."""
        bs = BalanceSheetService.generate(organisation)

        assert 'as_of' in bs
        assert 'total_assets' in bs
        assert 'total_liabilities' in bs
        assert 'total_equity' in bs
        # Balance sheet should balance
        assert bs['is_balanced'] is True


@pytest.mark.django_db
class TestIncomeStatementService:
    """Tests for Income Statement Service."""

    def test_generate_income_statement(self, organisation, user):
        """Test generating an income statement."""
        from django.utils import timezone

        # Create customer and invoice
        customer = Customer.objects.create(
            organisation=organisation,
            name='Test Customer',
            email='test@test.com'
        )

        invoice = InvoiceService.create_invoice(
            organisation=organisation,
            customer=customer,
            invoice_date=timezone.now().date(),
            lines=[{
                'account': organisation.accounts.get(code='4100').id,
                'description': 'Services',
                'quantity': 1,
                'unit_price': 1000,
            }],
            created_by=user,
        )
        InvoiceService.send_invoice(invoice, user)

        # Generate income statement
        is_report = IncomeStatementService.generate(organisation)

        assert 'revenue' in is_report
        assert 'expenses' in is_report
        assert 'total_revenue' in is_report
        assert 'net_income' in is_report


@pytest.mark.django_db
class TestAgedReceivablesService:
    """Tests for Aged Receivables Service."""

    def test_generate_aged_receivables(self, organisation, user):
        """Test generating aged receivables report."""
        from django.utils import timezone
        from datetime import timedelta

        # Create customer and overdue invoice
        customer = Customer.objects.create(
            organisation=organisation,
            name='Test Customer',
            email='test@test.com'
        )

        invoice = InvoiceService.create_invoice(
            organisation=organisation,
            customer=customer,
            invoice_date=timezone.now().date() - timedelta(days=60),
            lines=[{
                'account': organisation.accounts.get(code='4100').id,
                'description': 'Old services',
                'quantity': 1,
                'unit_price': 500,
            }],
            created_by=user,
        )
        InvoiceService.send_invoice(invoice, user)

        # Generate report
        ar = AgedReceivablesService.generate(organisation)

        assert 'aging' in ar
        assert 'customer_aging' in ar


@pytest.mark.django_db
class TestAgedPayablesService:
    """Tests for Aged Payables Service."""

    def test_generate_aged_payables(self, organisation, user):
        """Test generating aged payables report."""
        from django.utils import timezone
        from datetime import timedelta

        vendor = Vendor.objects.create(
            organisation=organisation,
            name='Test Vendor',
            email='test@vendor.com'
        )

        bill = BillService.create_bill(
            organisation=organisation,
            vendor=vendor,
            bill_date=timezone.now().date() - timedelta(days=60),
            due_date=timezone.now().date() - timedelta(days=30),
            lines=[{
                'account': organisation.accounts.get(code='5110').id,
                'description': 'Old services',
                'quantity': 1,
                'unit_price': 500,
            }],
            created_by=user,
        )
        BillService.post_bill(bill, user)

        # Generate report
        ap = AgedPayablesService.generate(organisation)

        assert 'aging' in ap
        assert 'vendor_aging' in ap


@pytest.mark.django_db
class TestDashboardService:
    """Tests for Dashboard Service."""

    def test_get_overview(self, organisation):
        """Test getting dashboard overview."""
        overview = DashboardService.get_overview(organisation)

        assert 'cash_balance' in overview
        assert 'ar_balance' in overview
        assert 'ap_balance' in overview
        assert 'monthly_revenue' in overview
        assert 'monthly_expenses' in overview

    def test_get_cash_flow_trend(self, organisation):
        """Test getting cash flow trend."""
        trend = DashboardService.get_cash_flow_trend(organisation, months=6)

        assert len(trend) == 6
        for month in trend:
            assert 'month' in month
            assert 'inflows' in month
            assert 'outflows' in month
            assert 'net' in month
