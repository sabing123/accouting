import pytest
from decimal import Decimal
from django.utils import timezone

from ledger.models import Account, AccountType, JournalEntry, JournalEntryLine, FiscalYear, FiscalPeriod
from ledger.services import ChartOfAccountsService, JournalEntryService


@pytest.mark.django_db
class TestChartOfAccountsService:
    """Tests for Chart of Accounts Service."""

    def test_setup_default_chart_of_accounts(self, organisation):
        """Test that default chart of accounts is created."""
        accounts = ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        # Should have created accounts
        assert len(accounts) > 0

        # Check for specific account types
        asset_accounts = Account.objects.filter(
            organisation=organisation,
            account_type__name='asset'
        )
        assert asset_accounts.exists()

        # Check cash account exists
        cash_account = Account.objects.filter(
            organisation=organisation,
            code='1000'
        ).first()
        assert cash_account is not None
        assert cash_account.name == 'Cash and Cash Equivalents'
        assert cash_account.is_bank_account is True

    def test_create_account(self, organisation):
        """Test creating a new account."""
        # Setup chart of accounts first
        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        account_type = AccountType.objects.get(
            organisation=organisation,
            name='expense'
        )

        account = ChartOfAccountsService.create_account(
            organisation=organisation,
            code='5999',
            name='Miscellaneous Expense',
            account_type=account_type,
        )

        assert account.code == '5999'
        assert account.name == 'Miscellaneous Expense'
        assert account.account_type.name == 'expense'

    def test_duplicate_account_code_raises_error(self, organisation):
        """Test that duplicate account codes raise an error."""
        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        account_type = AccountType.objects.get(
            organisation=organisation,
            name='expense'
        )

        with pytest.raises(ValueError, match="already exists"):
            ChartOfAccountsService.create_account(
                organisation=organisation,
                code='5100',  # Already exists in defaults
                name='Duplicate Account',
                account_type=account_type,
            )


@pytest.mark.django_db
class TestJournalEntryService:
    """Tests for Journal Entry Service."""

    def test_create_balanced_journal_entry(self, organisation, user):
        """Test creating a balanced journal entry."""
        # Setup chart of accounts
        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        cash_account = Account.objects.get(organisation=organisation, code='1000')
        revenue_account = Account.objects.get(organisation=organisation, code='4100')

        entry = JournalEntryService.create_entry(
            organisation=organisation,
            date=timezone.now().date(),
            description='Test entry',
            lines=[
                {'account': cash_account.id, 'debit': 1000, 'credit': 0},
                {'account': revenue_account.id, 'debit': 0, 'credit': 1000},
            ],
            created_by=user,
        )

        assert entry is not None
        assert entry.description == 'Test entry'
        assert entry.total_debit == Decimal('1000')
        assert entry.total_credit == Decimal('1000')
        assert entry.is_balanced() is True
        assert entry.lines.count() == 2

    def test_unbalanced_entry_raises_error(self, organisation, user):
        """Test that unbalanced entries raise an error."""
        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        cash_account = Account.objects.get(organisation=organisation, code='1000')
        revenue_account = Account.objects.get(organisation=organisation, code='4100')

        with pytest.raises(ValueError, match="balanced"):
            JournalEntryService.create_entry(
                organisation=organisation,
                date=timezone.now().date(),
                description='Unbalanced entry',
                lines=[
                    {'account': cash_account.id, 'debit': 1000, 'credit': 0},
                    {'account': revenue_account.id, 'debit': 0, 'credit': 500},  # Unbalanced!
                ],
                created_by=user,
            )

    def test_post_journal_entry(self, organisation, user):
        """Test posting a journal entry."""
        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        cash_account = Account.objects.get(organisation=organisation, code='1000')
        revenue_account = Account.objects.get(organisation=organisation, code='4100')

        entry = JournalEntryService.create_entry(
            organisation=organisation,
            date=timezone.now().date(),
            description='Test entry',
            lines=[
                {'account': cash_account.id, 'debit': 1000, 'credit': 0},
                {'account': revenue_account.id, 'debit': 0, 'credit': 1000},
            ],
            created_by=user,
        )

        # Post the entry
        JournalEntryService.post_entry(entry, user)

        entry.refresh_from_db()
        assert entry.status == JournalEntry.Status.POSTED
        assert entry.posted_by == user
        assert entry.posted_at is not None

        # Check account balances updated
        cash_account.refresh_from_db()
        revenue_account.refresh_from_db()
        assert cash_account.period_debit == Decimal('1000')
        assert revenue_account.period_credit == Decimal('1000')

    def test_void_journal_entry(self, organisation, user):
        """Test voiding a posted journal entry."""
        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        cash_account = Account.objects.get(organisation=organisation, code='1000')
        revenue_account = Account.objects.get(organisation=organisation, code='4100')

        entry = JournalEntryService.create_entry(
            organisation=organisation,
            date=timezone.now().date(),
            description='Test entry',
            lines=[
                {'account': cash_account.id, 'debit': 1000, 'credit': 0},
                {'account': revenue_account.id, 'debit': 0, 'credit': 1000},
            ],
            created_by=user,
        )

        # Post and then void
        JournalEntryService.post_entry(entry, user)
        JournalEntryService.void_entry(entry, user, 'Test void')

        entry.refresh_from_db()
        assert entry.status == JournalEntry.Status.VOIDED

        # Should have a reversing entry
        assert entry.reversing_entry is not None


@pytest.mark.django_db
class TestAccountModel:
    """Tests for Account model."""

    def test_account_hierarchy(self, organisation):
        """Test account parent-child relationship."""
        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        # 1000 is parent of 1100
        parent = Account.objects.get(organisation=organisation, code='1000')
        child = Account.objects.get(organisation=organisation, code='1100')

        assert child.parent == parent
        assert child.level == 1
        assert parent.level == 0

    def test_account_get_balance(self, organisation, user):
        """Test calculating account balance."""
        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        cash_account = Account.objects.get(organisation=organisation, code='1000')
        revenue_account = Account.objects.get(organisation=organisation, code='4100')

        # Create and post entry
        entry = JournalEntryService.create_entry(
            organisation=organisation,
            date=timezone.now().date(),
            description='Test entry',
            lines=[
                {'account': cash_account.id, 'debit': 5000, 'credit': 0},
                {'account': revenue_account.id, 'debit': 0, 'credit': 5000},
            ],
            created_by=user,
        )
        JournalEntryService.post_entry(entry, user)

        # Check balance
        balance = cash_account.get_balance()
        assert balance == Decimal('5000')


@pytest.mark.django_db
class TestFiscalYear:
    """Tests for Fiscal Year and Period models."""

    def test_create_fiscal_year(self, organisation):
        """Test creating a fiscal year."""
        today = timezone.now().date()
        from datetime import timedelta

        fy = FiscalYear.objects.create(
            organisation=organisation,
            name='FY 2024',
            start_date=today,
            end_date=today + timedelta(days=364),
        )

        assert fy.name == 'FY 2024'
        assert fy.status == FiscalYear.Status.OPEN

    def test_close_fiscal_year(self, organisation, user):
        """Test closing a fiscal year."""
        today = timezone.now().date()
        from datetime import timedelta

        fy = FiscalYear.objects.create(
            organisation=organisation,
            name='FY 2024',
            start_date=today,
            end_date=today + timedelta(days=364),
        )

        fy.close(user)

        assert fy.status == FiscalYear.Status.CLOSED
        assert fy.closed_by == user
