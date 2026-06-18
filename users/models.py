from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils.translation import gettext_lazy as _
import uuid


class UserManager(BaseUserManager):
    """Custom manager for User model with email-based authentication."""

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular user with the given email and password."""
        if not email:
            raise ValueError(_('The Email field must be set'))

        email = self.normalize_email(email)
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('is_active', False)  # Require email verification

        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        """Create and save a superuser with the given email and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError(_('Superuser must have is_staff=True.'))
        if extra_fields.get('is_superuser') is not True:
            raise ValueError(_('Superuser must have is_superuser=True.'))

        return self._create_user(email, password, **extra_fields)

    def _create_user(self, email, password=None, **extra_fields):
        """Internal method to create user."""
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user


class User(AbstractUser):
    """
    Custom User model using email as the primary identifier.
    Supports multi-tenant organisation memberships.
    """

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Remove username field (use email only)
    username = None

    # Email is the primary identifier
    email = models.EmailField(
        _('Email Address'),
        unique=True,
        db_index=True,
        error_messages={
            'unique': _("A user with that email already exists."),
        },
    )

    # Profile information
    first_name = models.CharField(_('First Name'), max_length=150)
    last_name = models.CharField(_('Last Name'), max_length=150)
    job_title = models.CharField(_('Job Title'), max_length=100, blank=True)
    avatar = models.ImageField(
        _('Avatar'),
        upload_to='users/avatars/',
        blank=True,
        null=True
    )
    phone = models.CharField(_('Phone'), max_length=20, blank=True)

    # Preferences
    timezone = models.CharField(_('Timezone'), max_length=50, default='America/New_York')
    language = models.CharField(_('Language'), max_length=10, default='en')
    date_format = models.CharField(_('Date Format'), max_length=20, default='MM/DD/YYYY')

    # Notification preferences
    email_notifications = models.BooleanField(_('Email Notifications'), default=True)
    weekly_report = models.BooleanField(_('Weekly Report'), default=True)

    # Two-factor authentication
    two_factor_enabled = models.BooleanField(_('2FA Enabled'), default=False)
    two_factor_secret = models.CharField(_('2FA Secret'), max_length=32, blank=True)

    # Security
    last_login_ip = models.GenericIPAddressField(_('Last Login IP'), null=True, blank=True)
    password_changed_at = models.DateTimeField(_('Password Changed'), null=True, blank=True)

    # Email verification
    email_verified = models.BooleanField(_('Email Verified'), default=False)
    verification_code = models.CharField(_('Verification Code'), max_length=64, blank=True)
    verification_code_expires = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    class Meta:
        db_table = 'users'
        verbose_name = _('User')
        verbose_name_plural = _('Users')
        ordering = ['email']

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_default_organisation(self):
        """Get the user's default organisation."""
        from organisations.models import OrganisationMembership

        membership = self.organisation_memberships.filter(is_default=True).first()
        if membership:
            return membership.organisation

        # Return first organisation if no default
        membership = self.organisation_memberships.first()
        if membership:
            return membership.organisation

    def get_organisations(self):
        """Get all organisations the user belongs to."""
        return self.organisation_memberships.filter(is_organisation__is_active=True)

    def is_admin_of(self, organisation):
        """Check if user is an admin or owner of an organisation."""
        from organisations.models import OrganisationMembership

        return self.organisation_memberships.filter(
            organisation=organisation,
            role__in=[OrganisationMembership.Role.OWNER, OrganisationMembership.Role.ADMIN]
        ).exists()

    def is_member_of(self, organisation):
        """Check if user is a member of an organisation."""
        return self.organisation_memberships.filter(organisation=organisation).exists()

    def generate_verification_code(self):
        """Generate a verification code for email verification."""
        import secrets
        from django.utils import timezone
        from datetime import timedelta

        self.verification_code = secrets.token_urlsafe(32)
        self.verification_code_expires = timezone.now() + timedelta(hours=24)
        self.save(update_fields=['verification_code', 'verification_code_expires'])
        return self.verification_code

    def verify_email(self, code):
        """Verify user's email with the provided verification code."""
        from django.utils import timezone

        if self.verification_code != code:
            return False

        if self.verification_code_expires < timezone.now():
            return False

        self.email_verified = True
        self.is_active = True
        self.verification_code = ''
        self.verification_code_expires = None
        self.save()
        return True


class UserProfile(models.Model):
    """Extended user profile information."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    # Social links
    linkedin = models.URLField(blank=True)
    twitter = models.CharField(max_length=50, blank=True)

    # Bio
    bio = models.TextField(max_length=500, blank=True)

    # Address
    address_line1 = models.CharField(max_length=255, blank=True)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state_province = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_profiles'
        verbose_name = _('User Profile')
        verbose_name_plural = _('User Profiles')

    def __str__(self):
        return f"Profile for {self.user.email}"


class UserActivity(models.Model):
    """Track user activities for audit purposes."""

    class ActionType(models.TextChoices):
        LOGIN = 'login', _('Login')
        LOGOUT = 'logout', _('Logout')
        PASSWORD_CHANGE = 'password_change', _('Password Change')
        PROFILE_UPDATE = 'profile_update', _('Profile Update')
        ORG_SWITCH = 'org_switch', _('Organisation Switch')
        LOGIN_FAIL = 'login_fail', _('Failed Login')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='activities'
    )
    action = models.CharField(max_length=20, choices=ActionType.choices)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'user_activities'
        verbose_name = _('User Activity')
        verbose_name_plural = _('User Activities')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.action}"
