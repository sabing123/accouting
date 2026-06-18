from django.db import transaction
from django.utils import timezone
from datetime import timedelta
import secrets
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser
    from organisations.models import Organisation, OrganisationMembership


class OrganisationService:
    """Service layer for organisation operations."""

    @staticmethod
    def create_organisation(
        name: str,
        user: 'AbstractUser',
        industry: str = '',
        country: str = 'US',
        **kwargs
    ) -> 'Organisation':
        """
        Create a new organisation with the user as owner.

        Creates:
        - Organisation record
        - Owner membership
        - Default domain
        - Trial subscription
        """
        from organisations.models import Organisation, OrganisationMembership, OrganisationDomain

        with transaction.atomic():
            org = Organisation.objects.create(
                name=name,
                industry=industry,
                country=country,
                email=user.email,
                trial_ends_at=timezone.now() + timedelta(days=14),
                **kwargs
            )

            # Add creator as owner
            OrganisationMembership.objects.create(
                organisation=org,
                user=user,
                role=OrganisationMembership.Role.OWNER,
                is_default=True
            )

            # Create primary domain
            OrganisationDomain.objects.create(
                organisation=org,
                domain=f"{org.slug}.accountingsaas.com",
                is_primary=True
            )

            return org

    @staticmethod
    def update_organisation(org: 'Organisation', **kwargs) -> 'Organisation':
        """Update organisation details."""
        for field, value in kwargs.items():
            if hasattr(org, field):
                setattr(org, field, value)
        org.save()
        return org

    @staticmethod
    def delete_organisation(org: 'Organisation', user: 'AbstractUser') -> bool:
        """Soft delete an organisation (only by owner)."""
        from organisations.models import OrganisationMembership

        membership = OrganisationMembership.objects.filter(
            organisation=org,
            user=user,
            role=OrganisationMembership.Role.OWNER
        ).first()

        if not membership and not user.is_superuser:
            return False

        org.is_active = False
        org.save(update_fields=['is_active'])
        return True

    @staticmethod
    def invite_member(
        org: 'Organisation',
        email: str,
        role: str,
        invited_by: 'AbstractUser'
    ) -> 'OrganisationInvitation':
        """Invite a new member to the organisation."""
        from organisations.models import OrganisationInvitation

        # Check if already invited
        existing = OrganisationInvitation.objects.filter(
            organisation=org,
            email=email,
            status=OrganisationInvitation.Status.PENDING
        ).first()

        if existing:
            return existing

        invitation = OrganisationInvitation.objects.create(
            organisation=org,
            email=email,
            role=role,
            invited_by=invited_by
        )

        return invitation

    @staticmethod
    def accept_invitation(token: str, user: 'AbstractUser') -> 'OrganisationMembership':
        """Accept an invitation to join an organisation."""
        from organisations.models import OrganisationInvitation, OrganisationMembership

        invitation = OrganisationInvitation.objects.filter(
            token=token,
            status=OrganisationInvitation.Status.PENDING
        ).first()

        if not invitation:
            raise ValueError("Invalid or expired invitation.")

        if invitation.expires_at < timezone.now():
            invitation.status = OrganisationInvitation.Status.EXPIRED
            invitation.save()
            raise ValueError("Invitation has expired.")

        with transaction.atomic():
            # Create membership
            membership = OrganisationMembership.objects.create(
                organisation=invitation.organisation,
                user=user,
                role=invitation.role
            )

            # Update invitation
            invitation.status = OrganisationInvitation.Status.ACCEPTED
            invitation.save()

            return membership

    @staticmethod
    def remove_member(org: 'Organisation', user_id, removed_by: 'AbstractUser') -> bool:
        """Remove a member from organisation."""
        from organisations.models import OrganisationMembership
        from users.models import User

        try:
            membership = OrganisationMembership.objects.select_related('user').get(
                organisation=org,
                user_id=user_id
            )
        except OrganisationMembership.DoesNotExist:
            return False

        # Can't remove the last owner
        if membership.role == OrganisationMembership.Role.OWNER:
            owners_count = OrganisationMembership.objects.filter(
                organisation=org,
                role=OrganisationMembership.Role.OWNER
            ).count()
            if owners_count <= 1:
                raise ValueError("Cannot remove the last owner.")

        membership.delete()
        return True

    @staticmethod
    def update_member_role(
        org: 'Organisation',
        user_id,
        new_role: str,
        updated_by: 'AbstractUser'
    ) -> 'OrganisationMembership':
        """Update a member's role."""
        from organisations.models import OrganisationMembership

        membership = OrganisationMembership.objects.get(
            organisation=org,
            user_id=user_id
        )

        # Can't demote the last owner
        if membership.role == OrganisationMembership.Role.OWNER and new_role != OrganisationMembership.Role.OWNER:
            owners_count = OrganisationMembership.objects.filter(
                organisation=org,
                role=OrganisationMembership.Role.OWNER
            ).count()
            if owners_count <= 1:
                raise ValueError("Cannot demote the last owner.")

        membership.role = new_role
        membership.save()
        return membership

    @staticmethod
    def get_user_organisations(user: 'AbstractUser') -> List['Organisation']:
        """Get all organisations a user belongs to."""
        return Organisation.objects.filter(
            memberships__user=user,
            is_active=True
        ).distinct()

    @staticmethod
    def switch_organisation(user: 'AbstractUser', org: 'Organisation') -> bool:
        """Set the default organisation for a user."""
        from organisations.models import OrganisationMembership

        membership = OrganisationMembership.objects.filter(
            user=user,
            organisation=org
        ).first()

        if not membership:
            return False

        membership.is_default = True
        membership.save()
        return True
