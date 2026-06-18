from django.http import HttpRequest
from django.utils.deprecation import MiddlewareMixin
from django.utils.functional import SimpleLazyObject
from django.conf import settings
from threading import local
from typing import Optional

_thread_locals = local()


def get_current_tenant():
    """Get the current tenant from thread local storage."""
    return getattr(_thread_locals, 'tenant', None)


def set_current_tenant(tenant):
    """Set the current tenant in thread local storage."""
    _thread_locals.tenant = tenant


def clear_current_tenant():
    """Clear the current tenant from thread local storage."""
    if hasattr(_thread_locals, 'tenant'):
        del _thread_locals.tenant


class TenantMiddleware(MiddlewareMixin):
    """
    Middleware that identifies the current tenant based on hostname.

    Supports both subdomain-based tenancy (company.accountingsaas.com)
    and custom domain tenancy (company.com).
    """

    def process_request(self, request):
        """Process request and set tenant based on hostname."""
        request.tenant = None
        request.tenant_id = None

        host = self._get_host(request)
        if not host:
            return None

        # Skip for public domains
        if host in self._get_public_domains():
            return None

        tenant = self._get_tenant_from_host(host)
        if tenant:
            request.tenant = tenant
            request.tenant_id = tenant.id
            set_current_tenant(tenant)

        return None

    def process_response(self, request, response):
        """Clear tenant from thread local after response."""
        clear_current_tenant()
        return response

    def process_exception(self, request, exception):
        """Clear tenant on exceptions."""
        clear_current_tenant()
        return None

    def _get_host(self, request: HttpRequest) -> str:
        """Extract hostname from request, removing port."""
        host = request.get_host().split(':')[0]
        return host.lower()

    def _get_public_domains(self):
        """Get list of public domains that don't map to tenants."""
        public_domains = getattr(settings, 'PUBLIC_DOMAINS', [
            'localhost',
            '127.0.0.1',
            'accountingsaas.com',
            'www.accountingsaas.com',
            'app.accountingsaas.com',
        ])
        return public_domains

    def _get_tenant_from_host(self, host: str):
        """Get tenant from hostname."""
        from organisations.models import OrganisationDomain, Organisation

        # First try exact domain match (custom domains)
        try:
            domain = OrganisationDomain.objects.filter(
                domain=host,
                is_verified=True
            ).select_related('organisation').first()

            if domain and domain.organisation.is_active:
                return domain.organisation
        except Exception:
            pass

        # Then try subdomain extraction (subdomain.accountingsaas.com)
        base_domain = getattr(settings, 'BASE_DOMAIN', 'accountingsaas.com')

        if host.endswith(f'.{base_domain}'):
            subdomain = host[:-len(f'.{base_domain}')]
            if subdomain and subdomain not in ('www', 'app', 'api', 'admin'):
                try:
                    org = Organisation.objects.filter(
                        slug=subdomain,
                        is_active=True
                    ).first()
                    return org
                except Exception:
                    pass

        # Local development: use subdomain.localhost
        if host.endswith('.localhost'):
            subdomain = host.replace('.localhost', '')
            if subdomain and subdomain not in ('www', 'app', 'api', 'admin'):
                try:
                    org = Organisation.objects.filter(
                        slug=subdomain,
                        is_active=True
                    ).first()
                    return org
                except Exception:
                    pass

        return None


class TenantContextMixin:
    """Mixin to add tenant context to views."""

    def get_tenant(self):
        return get_current_tenant()

    def dispatch(self, request, *args, **kwargs):
        tenant = request.tenant
        if not tenant:
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied("No tenant context found")
        return super().dispatch(request, *args, **kwargs)
