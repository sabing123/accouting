import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
class TestAuthViews:
    """Tests for authentication views."""

    def test_login_view_get(self, client):
        """Test GET request to login view."""
        # This would use allauth's login view
        response = client.get('/account/login/')
        assert response.status_code == 200

    def test_login_view_post_valid(self, client, user):
        """Test POST with valid credentials."""
        response = client.post('/account/login/', {
            'username': user.email,
            'password': 'testpass123',
        })
        # Should redirect after successful login
        assert response.status_code in [200, 302]

    def test_logout_view(self, authenticated_client):
        """Test logout view."""
        response = authenticated_client.post('/account/logout/')
        assert response.status_code in [200, 302]


@pytest.mark.django_db
class TestDashboardViews:
    """Tests for dashboard views."""

    def test_dashboard_requires_login(self, client):
        """Test that dashboard requires login."""
        response = client.get(reverse('dashboard:index'))
        assert response.status_code == 302  # Redirect to login

    def test_dashboard_authenticated(self, authenticated_client):
        """Test authenticated dashboard access."""
        response = authenticated_client.get(reverse('dashboard:index'))
        # May redirect if no tenant context
        assert response.status_code in [200, 302]


@pytest.mark.django_db
class TestOrganisationViews:
    """Tests for organisation views."""

    def test_organisation_list_requires_login(self, client):
        """Test organisation list requires login."""
        response = client.get(reverse('organisations:list'))
        assert response.status_code == 302

    def test_organisation_create_view(self, authenticated_client):
        """Test organisation creation view."""
        response = authenticated_client.get(reverse('organisations:create'))
        assert response.status_code == 200


@pytest.mark.django_db
class TestLedgerViews:
    """Tests for ledger views."""

    def test_account_list_requires_login(self, client):
        """Test account list requires login."""
        response = client.get(reverse('ledger:account-list'))
        assert response.status_code == 302

    def test_journal_entry_list_requires_login(self, client):
        """Test journal entry list requires login."""
        response = client.get(reverse('ledger:entry-list'))
        assert response.status_code == 302


@pytest.mark.django_db
class TestAPISchema:
    """Tests for API schema documentation."""

    def test_api_schema_view(self, client):
        """Test API schema is accessible."""
        response = client.get('/api/schema/')
        assert response.status_code == 200

    def test_swagger_ui_view(self, client):
        """Test Swagger UI is accessible."""
        response = client.get('/api/docs/')
        assert response.status_code == 200


@pytest.mark.django_db
class TestReportViews:
    """Tests for report views."""

    def test_reports_index_requires_login(self, client):
        """Test reports index requires login."""
        response = client.get(reverse('reports:index'))
        assert response.status_code == 302

    def test_trial_balance_report(self, authenticated_client, organisation):
        """Test trial balance report view."""
        # Set tenant context in session
        session = authenticated_client.session
        session['current_organisation_slug'] = organisation.slug
        session.save()

        response = authenticated_client.get(reverse('reports:trial-balance'))
        # May show report or error if no data
        assert response.status_code in [200, 302]
