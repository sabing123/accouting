from django import forms
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column

from payables.models import Vendor, Bill


class VendorForm(forms.ModelForm):
    """Form for creating/editing vendors."""

    class Meta:
        model = Vendor
        fields = [
            'name', 'display_name', 'vendor_number',
            'contact_name', 'email', 'phone', 'website',
            'address_line1', 'address_line2', 'city', 'state_province', 'postal_code', 'country',
            'tax_id', 'tax_code', 'payment_terms',
            'expense_account', 'payable_account',
            'currency', 'credit_limit', 'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'Vendor name'}),
            'display_name': forms.TextInput(attrs={'placeholder': 'Display name (if different)'}),
            'contact_name': forms.TextInput(attrs={'placeholder': 'Primary contact person'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://example.com'}),
        }

    def __init__(self, organisation, *args, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)

        # Filter accounts by organization
        from ledger.models import Account
        self.fields['expense_account'].queryset = Account.objects.filter(
            organisation=organisation,
            account_type__name='expense',
            is_active=True
        )
        self.fields['payable_account'].queryset = Account.objects.filter(
            organisation=organisation,
            account_type__name='liability',
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
                Column('vendor_number', css_class='col-md-4'),
                Column('contact_name', css_class='col-md-8'),
            ),
            Row(
                Column('email', css_class='col-md-4'),
                Column('phone', css_class='col-md-4'),
                Column('website', css_class='col-md-4'),
            ),
            'address_line1',
            'address_line2',
            Row(
                Column('city', css_class='col-md-4'),
                Column('state_province', css_class='col-md-4'),
                Column('postal_code', css_class='col-md-4'),
            ),
            'country',
            Row(
                Column('tax_id', css_class='col-md-6'),
                Column('tax_code', css_class='col-md-6'),
            ),
            Row(
                Column('payment_terms', css_class='col-md-4'),
                Column('currency', css_class='col-md-4'),
                Column('credit_limit', css_class='col-md-4'),
            ),
            Row(
                Column('expense_account', css_class='col-md-6'),
                Column('payable_account', css_class='col-md-6'),
            ),
            'notes',
        )


class BillForm(forms.ModelForm):
    """Form for creating/editing bills."""

    class Meta:
        model = Bill
        fields = [
            'vendor', 'bill_date', 'due_date', 'vendor_invoice_number',
            'purchase_order', 'description', 'notes',
        ]
        widgets = {
            'bill_date': forms.DateInput(attrs={'type': 'date'}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, organisation, *args, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)

        from payables.models import Vendor
        self.fields['vendor'].queryset = Vendor.objects.filter(
            organisation=organisation,
            is_active=True
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column('vendor', css_class='col-md-6'),
                Column('vendor_invoice_number', css_class='col-md-6'),
            ),
            Row(
                Column('bill_date', css_class='col-md-4'),
                Column('due_date', css_class='col-md-4'),
                Column('purchase_order', css_class='col-md-4'),
            ),
            'description',
            'notes',
        )


class PaymentForm(forms.Form):
    """Form for creating vendor payments."""

    vendor = forms.ModelChoiceField(queryset=Vendor.objects.none())
    payment_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    amount = forms.DecimalField(max_digits=20, decimal_places=2)
    reference = forms.CharField(max_length=100, required=False)
    memo = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}), required=False)

    def __init__(self, organisation, *args, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)

        from payables.models import Vendor
        self.fields['vendor'].queryset = Vendor.objects.filter(
            organisation=organisation,
            is_active=True
        )
