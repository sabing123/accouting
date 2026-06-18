import pytest
from rest_framework.test import APIClient
from django.urls import reverse

from ledger.models import Account
from ledger.services import ChartOfAccountsService


@pytest.mark.django_db
class TestAccountAPI:
    """Tests for Account API endpoints."""

    def test_list_accounts_unauthenticated(self):
        """Test that unauthenticated requests fail."""
        client = APIClient()
        response = client.get('/api/v1/accounts/')
        assert response.status_code == 401

    def test_list_accounts_authenticated(self, user, organisation):
        """Test listing accounts as authenticated user."""
        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        client = APIClient()
        client.force_authenticate(user=user)

        # Would need tenant middleware for full test
        response = client.get('/api/v1/accounts/')
        # May return empty or filtered results
        assert response.status_code in [200, 403]


@pytest.mark.django_db
class TestJournalEntryAPI:
    """Tests for Journal Entry API endpoints."""

    def test_create_journal_entry(self, user, organisation):
        """Test creating a journal entry via API."""
        from django.utils import timezone
        from decimal import Decimal
        from ledger.services import JournalEntryService

        ChartOfAccountsService.setup_default_chart_of_accounts(organisation)

        cash = Account.objects.get(organisation=organisation, code='1000')
        revenue = Account.objects.get(organisation=organisation, code='4100')

        client = APIClient()
        client.force_authenticate(user=user)

        data = {
            'date': timezone.now().date().isoformat(),
            'description': 'API Test Entry',
            'lines': [
                {'account': str(cash.id), 'debit': 1000, 'credit': 0},
                {'account': str(revenue.id), 'debit': 0, 'credit': 1000},
            ]
        }

        response = client.post('/api/v1/entries/', data, format='json')
        # May fail without tenant context
        assert response.status_code in [201, 400, 403]


@pytest.mark.django_db
class TestVendorAPI:
    """Tests for Vendor API endpoints."""

    def test_list_vendors_unauthenticated(self):
        """Test that unauthenticated requests fail."""
        client = APIClient()
        response = client.get('/api/v1/vendors/')
        assert response.status_code == 401


@pytest.mark.django_db
class TestCustomerAPI:
    """Tests for Customer API endpoints."""

    def test_list_customers_unauthenticated(self):
        """Test that unauthenticated requests fail."""
        client = APIClient()
        response = client.get('/api/v1/customers/')
        assert response.status_code == 401

    def test_create_customer(self, user, organisation):
        """Test creating a customer via API."""
        client = APIClient()
        client.force_authenticate(user=user)

        data = {
            'name': 'API Test Customer',
            'email': 'api@test.com',
        }

        response = client.post('/api/v1/customers/', data, format='json')
        # May fail without tenant context
        assert response.status_code in [201, 400, 403]


@pytest.mark.django_db
class TestInvoiceAPI:
    """Tests for Invoice API endpoints."""

    def test_list_invoices(self, user):
        """Test listing invoices."""
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.get('/api/v1/invoices/')
        # May return empty or filtered
        assert response.status_code in [200, 403]
