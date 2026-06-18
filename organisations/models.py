from django.db import models
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django.utils.text import slugify
import uuid


class OrganisationManager(models.Manager):
    """Custom manager for organisations."""

    def get_queryset(self):
        return super().get_queryset()

    def active(self):
        return self.get_queryset().filter(is_active=True)

    def on_trial(self):
        return self.get_queryset().filter(
            subscription_status=Organisation.SubscriptionStatus.TRIAL
        )

    def subscribed(self):
        return self.get_queryset().filter(
            subscription_status=Organisation.SubscriptionStatus.SUBSCRIBED
        )


class Organisation(models.Model):
    """
    Multi-tenant organisation model supporting hierarchical company structures.
    Each organisation is a tenant in the SaaS platform.
    """

    class Type(models.TextChoices):
        PROPRIETORSHIP = 'proprietorship', _('Proprietorship')
        PARTNERSHIP = 'partnership', _('Partnership')
        LLC = 'llc', _('Limited Liability Company')
        CORPORATION = 'corporation', _('Corporation')
        NONPROFIT = 'nonprofit', _('Non-Profit')

    class Size(models.TextChoices):
        SOLO = 'solo', _('Solopreneur (1)')
        SMALL = 'small', _('Small (2-10)')
        MEDIUM = 'medium', _('Medium (11-50)')
        LARGE = 'large', _('Large (51-200)')
        ENTERPRISE = 'enterprise', _('Enterprise (200+)')

    class SubscriptionStatus(models.TextChoices):
        TRIAL = 'trial', _('Trial')
        SUBSCRIBED = 'subscribed', _('Subscribed')
        PAST_DUE = 'past_due', _('Past Due')
        CANCELLED = 'cancelled', _('Cancelled')
        EXPIRED = 'expired', _('Expired')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Basic info
    name = models.CharField(_('Organisation Name'), max_length=255)
    slug = models.SlugField(_('Slug'), max_length=255, unique=True, blank=True)
    legal_name = models.CharField(_('Legal Name'), max_length=255, blank=True)
    type = models.CharField(_('Type'), max_length=20, choices=Type.choices, default=Type.LLC)
    size = models.CharField(_('Size'), max_length=20, choices=Size.choices, default=Size.SMALL)
    industry = models.CharField(_('Industry'), max_length=100, blank=True)
    description = models.TextField(_('Description'), blank=True)

    # Contact
    email = models.EmailField(_('Email'), max_length=255)
    phone = models.CharField(_('Phone'), max_length=50, blank=True)
    website = models.URLField(_('Website'), blank=True)

    # Address
    address_line1 = models.CharField(_('Address Line 1'), max_length=255, blank=True)
    address_line2 = models.CharField(_('Address Line 2'), max_length=255, blank=True)
    city = models.CharField(_('City'), max_length=100, blank=True)
    state_province = models.CharField(_('State/Province'), max_length=100, blank=True)
    postal_code = models.CharField(_('Postal Code'), max_length=20, blank=True)
    country = models.CharField(_('Country'), max_length=100, blank=True)

    # Tax & Registration
    tax_id = models.CharField(_('Tax ID/EIN'), max_length=50, blank=True)
    registration_number = models.CharField(_('Registration Number'), max_length=100, blank=True)

    # Currency & Localization
    base_currency = models.CharField(_('Base Currency'), max_length=3, default='USD')
    timezone = models.CharField(_('Timezone'), max_length=50, default='America/New_York')
    date_format = models.CharField(_('Date Format'), max_length=20, default='MM/DD/YYYY')
    fiscal_year_start_month = models.IntegerField(
        _('Fiscal Year Start Month'),
        default=1,
        help_text=_('Month number (1-12) when fiscal year starts')
    )

    # Subscription
    subscription_status = models.CharField(
        _('Subscription Status'),
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.TRIAL
    )
    subscription_plan = models.CharField(_('Plan'), max_length=50, default='starter')
    stripe_customer_id = models.CharField(_('Stripe Customer ID'), max_length=255, blank=True)
    stripe_subscription_id = models.CharField(_('Stripe Subscription ID'), max_length=255, blank=True)

    # Trial
    trial_ends_at = models.DateTimeField(_('Trial Ends At'), null=True, blank=True)

    # Status
    is_active = models.BooleanField(_('Is Active'), default=True)
    is_verified = models.BooleanField(_('Is Verified'), default=False)

    # Parent (for multi-company structures)
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subsidiaries',
        verbose_name=_('Parent Organisation')
    )

    # Branding
    logo = models.ImageField(_('Logo'), upload_to='organisations/logos/', blank=True, null=True)
    primary_color = models.CharField(_('Primary Color'), max_length=7, default='#1a73e8')
    secondary_color = models.CharField(_('Secondary Color'), max_length=7, default='#e8f0fe')

    # Settings
    settings = models.JSONField(_('Settings'), default=dict, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrganisationManager()

    class Meta:
        db_table = 'organisations'
        verbose_name = _('Organisation')
        verbose_name_plural = _('Organisations')
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)

        # Ensure unique slug
        original_slug = self.slug
        counter = 1
        while Organisation.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
            self.slug = f"{original_slug}-{counter}"
            counter += 1

        if not self.legal_name:
            self.legal_name = self.name

        super().save(*args, **kwargs)

    @property
    def is_on_trial(self):
        from django.utils import timezone
        return self.subscription_status == self.SubscriptionStatus.TRIAL and \
               self.trial_ends_at and self.trial_ends_at > timezone.now()

    def add_member(self, user, role='member'):
        """Add a user as a member of this organisation."""
        from .models import OrganisationMembership
        return OrganisationMembership.objects.get_or_create(
            organisation=self,
            user=user,
            defaults={'role': role}
        )

    def remove_member(self, user):
        """Remove a user from this organisation."""
        from .models import OrganisationMembership
        OrganisationMembership.objects.filter(
            organisation=self,
            user=user
        ).delete()

    def get_members(self):
        """Get all members of this organisation."""
        return self.memberships.all().select_related('user')


class OrganisationDomain(models.Model):
    """
    Domain mapping for multi-tenant organisation identification.
    Supports both subdomain (company.accountingsaas.com) and custom domain (company.com).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='domains',
        verbose_name=_('Organisation')
    )
    domain = models.CharField(_('Domain'), max_length=253, unique=True)
    is_primary = models.BooleanField(_('Is Primary'), default=False)
    is_verified = models.BooleanField(_('Is Verified'), default=False)
    verification_token = models.CharField(_('Verification Token'), max_length=64, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organisation_domains'
        verbose_name = _('Organisation Domain')
        verbose_name_plural = _('Organisation Domains')
        ordering = ['-is_primary', 'domain']

    def __str__(self):
        return self.domain

    def save(self, *args, **kwargs):
        if not self.verification_token:
            import secrets
            self.verification_token = secrets.token_urlsafe(32)

        if self.is_primary:
            OrganisationDomain.objects.filter(
                organisation=self.organisation,
                is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)

        super().save(*args, **kwargs)


class OrganisationInvitation(models.Model):
    """Track invitations sent to join an organisation."""

    class Status(models.TextChoices):
        PENDING = 'pending', _('Pending')
        ACCEPTED = 'accepted', _('Accepted')
        DECLINED = 'declined', _('Declined')
        EXPIRED = 'expired', _('Expired')

    class Role(models.TextChoices):
        OWNER = 'owner', _('Owner')
        ADMIN = 'admin', _('Admin')
        ACCOUNTANT = 'accountant', _('Accountant')
        BOOKKEEPER = 'bookkeeper', _('Bookkeeper')
        VIEWER = 'viewer', _('Viewer')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='invitations',
        verbose_name=_('Organisation')
    )
    email = models.EmailField(_('Email'))
    role = models.CharField(_('Role'), max_length=20, choices=Role.choices, default=Role.BOOKKEEPER)
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='invitations_sent',
        verbose_name=_('Invited By')
    )
    token = models.CharField(_('Token'), max_length=64, unique=True)
    status = models.CharField(_('Status'), max_length=20, choices=Status.choices, default=Status.PENDING)
    expires_at = models.DateTimeField(_('Expires At'))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organisation_invitations'
        verbose_name = _('Organisation Invitation')
        verbose_name_plural = _('Organisation Invitations')
        ordering = ['-created_at']

    def __str__(self):
        return f"Invitation to {self.organisation.name} for {self.email}"

    def save(self, *args, **kwargs):
        if not self.token:
            import secrets
            self.token = secrets.token_urlsafe(32)

        if not self.expires_at:
            from django.utils import timezone
            from datetime import timedelta
            self.expires_at = timezone.now() + timedelta(days=7)

        super().save(*args, **kwargs)


class OrganisationMembership(models.Model):
    """Members of an organisation with role-based access control."""

    class Role(models.TextChoices):
        OWNER = 'owner', _('Owner')
        ADMIN = 'admin', _('Admin')
        ACCOUNTANT = 'accountant', _('Accountant')
        BOOKKEEPER = 'bookkeeper', _('Bookkeeper')
        VIEWER = 'viewer', _('Viewer')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='memberships',
        verbose_name=_('Organisation')
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='organisation_memberships',
        verbose_name=_('User')
    )
    role = models.CharField(_('Role'), max_length=20, choices=Role.choices, default=Role.BOOKKEEPER)
    is_default = models.BooleanField(_('Is Default'), default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organisation_memberships'
        verbose_name = _('Organisation Membership')
        verbose_name_plural = _('Organisation Memberships')
        constraints = [
            models.UniqueConstraint(
                fields=['organisation', 'user'],
                name='unique_membership'
            )
        ]
        ordering = ['-is_default', '-created_at']

    def __str__(self):
        return f"{self.user} - {self.organisation.name} ({self.role})"

    def save(self, *args, **kwargs):
        if self.is_default:
            OrganisationMembership.objects.filter(
                user=self.user,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class Department(models.Model):
    """Departments/cost centers within an organisation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.ForeignKey(
        Organisation,
        on_delete=models.CASCADE,
        related_name='departments'
    )
    name = models.CharField(_('Name'), max_length=255)
    code = models.CharField(_('Code'), max_length=20, blank=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children'
    )
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_departments'
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'departments'
        verbose_name = _('Department')
        verbose_name_plural = _('Departments')
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['organisation', 'code'],
                condition=models.Q(code__gt=''),
                name='unique_department_code'
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.organisation.name})"
