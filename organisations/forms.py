from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, HTML
from organisations.models import Organisation, OrganisationMembership, OrganisationInvitation


class OrganisationCreateForm(forms.ModelForm):
    """Form for creating a new organisation."""

    class Meta:
        model = Organisation
        fields = ['name', 'type', 'industry', 'country', 'base_currency']
        widgets = {
            'type': forms.Select(attrs={'class': 'form-select'}),
            'industry': forms.TextInput(attrs={'placeholder': 'e.g., Technology, Healthcare, Retail'}),
            'country': forms.TextInput(attrs={'placeholder': 'e.g., United States'}),
            'base_currency': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column('name', css_class='col-md-8'),
                Column('type', css_class='col-md-4'),
            ),
            Row(
                Column('industry', css_class='col-md-6'),
                Column('country', css_class='col-md-6'),
            ),
            Row(
                Column('base_currency', css_class='col-md-6'),
                css_class='col-md-12',
            ),
        )


class OrganisationUpdateForm(forms.ModelForm):
    """Form for updating organisation details."""

    class Meta:
        model = Organisation
        fields = [
            'name', 'legal_name', 'type', 'industry',
            'email', 'phone', 'website',
            'address_line1', 'address_line2', 'city', 'state_province', 'postal_code', 'country',
            'tax_id', 'registration_number',
            'base_currency', 'timezone', 'date_format', 'fiscal_year_start_month',
            'primary_color', 'secondary_color',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Organisation name'}),
            'legal_name': forms.TextInput(attrs={'placeholder': 'Legal name (if different from above)'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'industry': forms.TextInput(attrs={'placeholder': 'e.g., Technology'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://example.com'}),
            'address_line1': forms.TextInput(attrs={'placeholder': 'Street address'}),
            'address_line2': forms.TextInput(attrs={'placeholder': 'Apartment, suite, etc. (optional)'}),
            'city': forms.TextInput(attrs={'placeholder': 'City'}),
            'state_province': forms.TextInput(attrs={'placeholder': 'State/Province'}),
            'postal_code': forms.TextInput(attrs={'placeholder': 'ZIP/Postal code'}),
            'country': forms.TextInput(attrs={'placeholder': 'Country'}),
            'tax_id': forms.TextInput(attrs={'placeholder': 'Tax ID / EIN'}),
            'fiscal_year_start_month': forms.NumberInput(attrs={'min': 1, 'max': 12}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            HTML('<h5 class="card-title mb-3">Basic Information</h5>'),
            Row(
                Column('name', css_class='col-md-6'),
                Column('legal_name', css_class='col-md-6'),
            ),
            Row(
                Column('type', css_class='col-md-4'),
                Column('industry', css_class='col-md-4'),
                css_class='mb-4',
            ),
            HTML('<h5 class="card-title mb-3">Contact Information</h5>'),
            Row(
                Column('email', css_class='col-md-4'),
                Column('phone', css_class='col-md-4'),
                Column('website', css_class='col-md-4'),
            ),
            HTML('<h5 class="card-title mb-3 mt-4">Address</h5>'),
            'address_line1',
            'address_line2',
            Row(
                Column('city', css_class='col-md-4'),
                Column('state_province', css_class='col-md-4'),
                Column('postal_code', css_class='col-md-4'),
            ),
            'country',
            HTML('<h5 class="card-title mb-3 mt-4">Tax & Registration</h5>'),
            Row(
                Column('tax_id', css_class='col-md-6'),
                Column('registration_number', css_class='col-md-6'),
            ),
            HTML('<h5 class="card-title mb-3 mt-4">Accounting Settings</h5>'),
            Row(
                Column('base_currency', css_class='col-md-4'),
                Column('timezone', css_class='col-md-4'),
                Column('fiscal_year_start_month', css_class='col-md-4'),
            ),
            HTML('<h5 class="card-title mb-3 mt-4">Branding</h5>'),
            Row(
                Column('primary_color', css_class='col-md-6'),
                Column('secondary_color', css_class='col-md-6'),
            ),
        )


class MemberInviteForm(forms.Form):
    """Form for inviting a new member."""
    email = forms.EmailField(
        label=_('Email Address'),
        widget=forms.EmailInput(attrs={'placeholder': 'member@example.com'})
    )
    role = forms.ChoiceField(
        label=_('Role'),
        choices=OrganisationMembership.Role.choices,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column('email', css_class='col-md-8'),
                Column('role', css_class='col-md-4'),
            )
        )


class MemberRoleForm(forms.Form):
    """Form for changing a member's role."""
    role = forms.ChoiceField(
        label=_('Role'),
        choices=OrganisationMembership.Role.choices,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = True
        self.helper.add_input(Submit('submit', 'Update Role', css_class='btn-primary'))
        self.helper.layout = Layout('role')
