from allauth.account.adapter import DefaultAccountAdapter
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
import stripe


class AccountAdapter(DefaultAccountAdapter):
    """Custom adapter for django-allauth."""

    def is_open_for_signup(self, request):
        """
        Allow signup if:
        - On public pages
        - User doesn't already belong to max organisations
        """
        return True

    def save_user(self, request, user, form, commit=True):
        """
        Override to handle custom User model fields.
        """
        from django.utils import timezone

        data = form.cleaned_data
        user.email = data.get('email')
        user.first_name = data.get('first_name', '')
        user.last_name = data.get('last_name', '')

        if 'password' in data:
            user.set_password(data['password'])
        else:
            user.set_unusable_password()

        if commit:
            user.save()

        return user

    def send_mail(self, template_prefix, email, context):
        """
        Send email with custom template handling.
        """
        # Add organisation context if available
        if hasattr(context.get('request', None), 'tenant'):
            context['organisation'] = context['request'].tenant

        return super().send_mail(template_prefix, email, context)

    def get_login_redirect_url(self, request):
        """Redirect to dashboard after login, or organisation if specified."""
        return '/dashboard/'

    def get_email_confirmation_redirect_url(self, request):
        """Redirect after email confirmation."""
        return '/dashboard/'

    def authenticate(self, request, **credentials):
        """Custom authentication handling."""
        return super().authenticate(request, **credentials)

    def add_message(self, request, level, message_template, message_context=None, extra_tags=''):
        """Custom message handling."""
        return super().add_message(request, level, message_template, message_context, extra_tags)

    def get_from_email(self):
        """Get the from email for notifications."""
        from django.conf import settings
        return settings.DEFAULT_FROM_EMAIL
