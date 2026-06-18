from django import forms
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column

from receivables.models import Customer, Invoice


class CustomerForm(forms.ModelForm):
    """Form for creating/editing customers."""

    class Meta:
        model = Customer
        fields = [
            'name', 'display_name', 'customer_number',
            'contact_name', 'email', 'phone', 'mobile', 'website',
            'billing_address_line1', 'billing_address_line2',
            'billing_city', 'billing_state_province', 'billing_postal_code', 'billing_country',
            'same_as_billing',
            'shipping_address_line1', 'shipping_address_line2',
            'shipping_city', 'shipping_state_province', 'shipping_postal_code', 'shipping_country',
            'tax_id', 'tax_code', 'tax_exempt', 'payment_terms',
            'receivable_account', 'revenue_account',
            'currency', 'credit_limit', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Customer name'}),
            'display_name': forms.TextInput(attrs={'placeholder': 'Display name (if different)'}),
            'contact_name': forms.TextInput(attrs={'placeholder': 'Primary contact person'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://example.com'}),
        }

    def __init__(self, organisation, *args, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)

        from ledger.models import Account
        self.fields['receivable_account'].queryset = Account.objects.filter(
            organisation=organisation,
            account_type__name='asset',
            name__icontains='receivable',
            is_active=True
        )
        self.fields['revenue_account'].queryset = Account.objects.filter(
            organisation=organisation,
            account_type__name='income',
            is_active=True
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column('name', css_class='col-md-6'),
                Column('display_name', css_class='col-md-6'),
            ),
            Row(
                Column('customer_number', css_class='col-md-4'),
                Column('contact_name', css_class='col-md-8'),
            ),
            Row(
                Column('email', css_class='col-md-4'),
                Column('phone', css_class='col-md-4'),
                Column('mobile', css_class='col-md-4'),
            ),
            'website',
            HTML('<h5 class="card-title mb-3 mt-4">Billing Address</h5>'),
            'billing_address_line1',
            'billing_address_line2',
            Row(
                Column('billing_city', css_class='col-md-4'),
                Column('billing_state_province', css_class='col-md-4'),
                Column('billing_postal_code', css_class='col-md-4'),
            ),
            'billing_country',
            'same_as_billing',
            HTML('<h5 class="card-title mb-3 mt-4">Shipping Address</h5>'),
            'shipping_address_line1',
            'shipping_address_line2',
            Row(
                Column('shipping_city', css_class='col-md-4'),
                Column('shipping_state_province', css_class='col-md-4'),
                Column('shipping_postal_code', css_class='col-md-4'),
            ),
            'shipping_country',
            HTML('<h5 class="card-title mb-3 mt-4">Payment Settings</h5>'),
            Row(
                Column('payment_terms', css_class='col-md-4'),
                Column('currency', css_class='col-md-4'),
                Column('credit_limit', css_class='col-md-4'),
            ),
            Row(
                Column('receivable_account', css_class='col-md-6'),
                Column('revenue_account', css_class='col-md-6'),
            ),
            Row(
                Column('tax_id', css_class='col-md-4'),
                Column('tax_code', css_class='col-md-4'),
                Column('tax_exempt', css_class='col-md-4'),
            ),
            'notes',
        )


class InvoiceForm(forms.ModelForm):
    """Form for creating invoices."""

    class Meta:
        model = Invoice
        fields = [
            'customer', 'invoice_date', 'due_date', 'payment_terms',
            'description', 'notes', 'customer_notes',
        ]
        widgets = {
            'invoice_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, organisation, *args, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)

        from receivables.models import Customer
        self.fields['customer'].queryset = Customer.objects.filter(
            organisation=organisation,
            is_active=True
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
