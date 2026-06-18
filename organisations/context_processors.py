def tenant_context(request):
    """Add tenant context to all templates."""
    context = {
        'tenant': getattr(request, 'tenant', None),
        'tenant_id': getattr(request, 'tenant_id', None),
        'has_tenant': hasattr(request, 'tenant') and request.tenant is not None,
    }
    return context
