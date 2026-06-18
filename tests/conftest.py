import pytest
from django.contrib.auth import get_user_model
from organisations.models import Organisation, OrganisationMembership

User = get_user_model()


@pytest.fixture
def user():
    """Create a test user."""
    return User.objects.create_user(
        email='test@example.com',
        password='testpass123',
        first_name='Test',
        last_name='User'
    )


@pytest.fixture
def organisation(user):
    """Create a test organisation."""
    org = Organisation.objects.create(
        name='Test Company',
        email='info@testcompany.com',
        country='US'
    )
    org.add_member(user, role=OrganisationMembership.Role.OWNER)
    return org


@pytest.fixture
def authenticated_client(client, user):
    """Return an authenticated client."""
    client.force_login(user)
    return client


@pytest.fixture
def tenant_client(client, user, organisation):
    """Return a client with tenant context set."""
    client.force_login(user)
    client.session['current_organisation_slug'] = organisation.slug
    client.session.save()
    return client
