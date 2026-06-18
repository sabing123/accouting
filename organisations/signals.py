from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.db import transaction
from organisations.models import Organisation, OrganisationMembership, OrganisationDomain
from ledger.services import ChartOfAccountsService


@receiver(post_save, sender=Organisation)
def create_organisation_defaults(sender, instance, created, **kwargs):
    """
    Create default records for a new organisation:
    - Default member for creator
    - Default domain
    - Default chart of accounts
    """

    if created:
        from django.utils import timezone
        from datetime import timedelta

        # Set trial period
        if not instance.trial_ends_at:
            instance.trial_ends_at = timezone.now() + timedelta(days=14)

        with transaction.atomic():
            # Create primary domain (subdomain)
            OrganisationDomain.objects.get_or_create(
                organisation=instance,
                domain=f"{instance.slug}.accountingsaas.com",
                defaults={'is_primary': True}
            )


@receiver(post_save, sender=Organisation)
def setup_chart_of_accounts(sender, instance, created, **kwargs):
    """Setup default chart of accounts for new organisations."""
    if created:
        from django.db import transaction

        def setup_accounts():
            try:
                ChartOfAccountsService.setup_default_chart_of_accounts(instance)
            except Exception:
                # Log error but don't fail organisation creation
                import logging
                logger = logging.getLogger(__name__)
                logger.exception(f"Failed to create default chart of accounts for {instance}")

        transaction.on_commit(setup_accounts)


@receiver(post_save, sender=OrganisationMembership)
def handle_membership_created(sender, instance, created, **kwargs):
    """Handle new membership creation."""
    if created:
        # Set as default if it's the user's first membership
        if not instance.user.organisation_memberships.exists():
            instance.is_default = True
            instance.save(update_fields=['is_default'])
