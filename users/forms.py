from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit

from django.contrib.auth.forms import UserCreationForm, UserChangeForm, AuthenticationForm

User = get_user_model()


class CustomAuthenticationForm(AuthenticationForm):
    """Custom login form using email."""

    username = forms.EmailField(
        label=_('Email Address'),
        widget=forms.EmailInput(attrs={
            'autofocus': True,
            'placeholder': 'you@example.com',
            'class': 'form-control form-control-lg'
        })
    )

    password = forms.CharField(
        label=_('Password'),
        strip=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Enter your password'
        })
    )

    error_messages = {
        'invalid_login': _(
            "Please enter a correct email and password. Note that both "
            "fields may be case-sensitive."
        ),
        'inactive': _("This account is inactive."),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            'username',
            'password',
        )


class UserRegistrationForm(UserCreationForm):
    """User registration form."""

    first_name = forms.CharField(
        label=_('First Name'),
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'First name'})
    )
    last_name = forms.CharField(
        label=_('Last Name'),
        max_length=150,
        widget=forms.TextInput(attrs={'placeholder': 'Last name'})
    )
    email = forms.EmailField(
        label=_('Email Address'),
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com'})
    )
    password1 = forms.CharField(
        label=_('Password'),
        widget=forms.PasswordInput(attrs={'placeholder': 'Create a strong password'}),
    )
    password2 = forms.CharField(
        label=_('Confirm Password'),
        widget=forms.PasswordInput(attrs={'placeholder': 'Confirm your password'}),
    )

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column('first_name', css_class='col-md-6'),
                Column('last_name', css_class='col-md-6'),
            ),
            'email',
            Row(
                Column('password1', css_class='col-md-6'),
                Column('password2', css_class='col-md-6'),
            ),
        )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_('A user with this email already exists.'))
        return email


class UserProfileForm(forms.ModelForm):
    """User profile update form."""

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email',
            'job_title', 'phone',
            'timezone', 'language', 'date_format',
            'email_notifications', 'weekly_report',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'placeholder': 'First name'}),
            'last_name': forms.TextInput(attrs={'placeholder': 'Last name'}),
            'job_title': forms.TextInput(attrs={'placeholder': 'Accountant, Controller, CFO...'}),
            'phone': forms.TextInput(attrs={'placeholder': '+1 (555) 123-4567'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML('<h5 class="card-title mb-3">Personal Information</h5>'),
            Row(
                Column('first_name', css_class='col-md-6'),
                Column('last_name', css_class='col-md-6'),
            ),
            'email',
            Row(
                Column('job_title', css_class='col-md-6'),
                Column('phone', css_class='col-md-6'),
            ),
            HTML('<h5 class="card-title mb-3 mt-4">Preferences</h5>'),
            Row(
                Column('timezone', css_class='col-md-4'),
                Column('language', css_class='col-md-4'),
                Column('date_format', css_class='col-md-4'),
            ),
            HTML('<h5 class="card-title mb-3 mt-4">Notifications</h5>'),
            'email_notifications',
            'weekly_report',
        )


class UserAdminChangeForm(UserChangeForm):
    """Form for admins to update users."""

    class Meta:
        model = User
        fields = '__all__'


class UserAdminCreationForm(UserCreationForm):
    """Form for admins to create users."""

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name')


class PasswordChangeForm(forms.Form):
    """Password change form for profile page."""

    current_password = forms.CharField(
        label=_('Current Password'),
        widget=forms.PasswordInput
    )
    new_password = forms.CharField(
        label=_('New Password'),
        widget=forms.PasswordInput
    )
    confirm_password = forms.CharField(
        label=_('Confirm New Password'),
        widget=forms.PasswordInput
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            'current_password',
            'new_password',
            'confirm_password',
        )

    def clean_current_password(self):
        current_password = self.cleaned_data.get('current_password')
        if not self.user.check_password(current_password):
            raise forms.ValidationError(_('Current password is incorrect.'))
        return current_password

    def clean_confirm_password(self):
        new_password = self.cleaned_data.get('new_password')
        confirm_password = self.cleaned_data.get('confirm_password')
        if new_password and new_password != confirm_password:
            raise forms.ValidationError(_('Passwords do not match.'))
        return confirm_password

    def save(self, commit=True):
        password = self.cleaned_data['new_password']
        self.user.set_password(password)
        if commit:
            self.user.save()
        return self.user
