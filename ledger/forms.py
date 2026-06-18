from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Submit, HTML, Div
from crispy_forms.bootstrap import FieldWithButtons, StrictButton

from ledger.models import Account, AccountType, AccountCategory, JournalEntry, JournalEntryLine
from django.core.exceptions import ValidationError


class AccountForm(forms.ModelForm):
    """Form for creating/editing accounts."""

    class Meta:
        model = Account
        fields = [
            'code', 'name', 'account_type', 'category',
            'description', 'parent', 'is_header',
            'is_bank_account', 'is_reconcilable',
            'tax_rate', 'tax_code', 'opening_balance', 'tags',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'tags': forms.TextInput(attrs={'placeholder': 'Comma-separated tags'}),
        }

    def __init__(self, organisation, *args, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)

        # Filter related fields by organization
        self.fields['account_type'].queryset = AccountType.objects.filter(
            organisation=organisation
        )
        self.fields['category'].queryset = AccountCategory.objects.filter(
            organisation=organisation
        )
        self.fields['parent'].queryset = Account.objects.filter(
            organisation=organisation,
            is_header=True
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column('code', css_class='col-md-4'),
                Column('name', css_class='col-md-8'),
            ),
            Row(
                Column('account_type', css_class='col-md-6'),
                Column('category', css_class='col-md-6'),
            ),
            'description',
            Row(
                Column('parent', css_class='col-md-6'),
                Column('tags', css_class='col-md-6'),
            ),
            HTML('<hr class="my-3"><h5 class="card-title mb-3">Settings</h5>'),
            Row(
                Column('is_header', css_class='col-md-4'),
                Column('is_bank_account', css_class='col-md-4'),
                Column('is_reconcilable', css_class='col-md-4'),
            ),
            HTML('<hr class="my-3"><h5 class="card-title mb-3">Tax Settings</h5>'),
            Row(
                Column('tax_code', css_class='col-md-6'),
                Column('tax_rate', css_class='col-md-6'),
            ),
            HTML('<hr class="my-3"><h5 class="card-title mb-3">Opening Balance</h5>'),
            Row(
                Column('opening_balance', css_class='col-md-6'),
            ),
        )

    def clean_code(self):
        code = self.cleaned_data.get('code')
        existing = Account.objects.filter(
            organisation=self.organisation,
            code=code
        ).exclude(pk=self.instance.pk)
        if existing.exists():
            raise ValidationError(_('Account with this code already exists.'))
        return code


class JournalEntryLineForm(forms.Form):
    """Form for a single journal entry line."""

    def __init__(self, organisation, *args, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)

        # Fields
        self.fields['account'] = forms.ModelChoiceField(
            queryset=Account.objects.filter(
                organisation=organisation,
                is_active=True,
                allow_transactions=True,
            ).order_by('code'),
            widget=forms.Select(attrs={'class': 'form-select'}),
        )

        self.fields['debit'] = forms.DecimalField(
            required=False,
            max_digits=20,
            decimal_places=2,
            min_value=0,
            widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
        )

        self.fields['credit'] = forms.DecimalField(
            required=False,
            max_digits=20,
            decimal_places=2,
            min_value=0,
            widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
        )

        self.fields['description'] = forms.CharField(
            required=False,
            max_length=255,
            widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Line description'}),
        )

    def clean(self):
        cleaned_data = super().clean()
        debit = cleaned_data.get('debit')
        credit = cleaned_data.get('credit')

        if not debit and not credit:
            raise ValidationError(_('Enter either a debit or credit amount.'))
        if debit and credit:
            raise ValidationError(_('A line cannot have both debit and credit amounts.'))

        return cleaned_data


class JournalEntryForm(forms.ModelForm):
    """Form for creating/editing journal entries."""

    # Dynamic line set
    lines = forms.Field(required=False)

    class Meta:
        model = JournalEntry
        fields = ['date', 'reference', 'description', 'entry_type', 'memo', 'fiscal_period']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Invoice #, PO #, etc.'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'memo': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, organisation, *args, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)

        # Set queryset for fiscal period
        self.fields['fiscal_period'].queryset = JournalEntry.objects.none()

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column('date', css_class='col-md-4'),
                Column('reference', css_class='col-md-4'),
                Column('entry_type', css_class='col-md-4'),
            ),
            'description',
            'memo',
        )


class QuickJournalEntryForm(forms.Form):
    """Simplified form for quick journal entry creation."""

    date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'value': timezone.now().date()}))
    description = forms.CharField(widget=forms.Textarea(attrs={'rows': 2}))

    # Simplified: one debit and one credit account
    debit_account = forms.ModelChoiceField(queryset=Account.objects.none())
    debit_amount = forms.DecimalField(max_digits=20, decimal_places=2, min_value=0)
    credit_account = forms.ModelChoiceField(queryset=Account.objects.none())
    credit_amount = forms.DecimalField(max_digits=20, decimal_places=2, min_value=0)
    memo = forms.CharField(max_length=255, required=False, widget=forms.TextInput())

    def __init__(self, organisation, *args, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)

        accounts = Account.objects.filter(
            organisation=organisation,
            is_active=True,
            allow_transactions=True,
        ).order_by('code')

        self.fields['debit_account'].queryset = accounts
        self.fields['credit_account'].queryset = accounts

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Row(
                Column('date', css_class='col-md-6'),
                Column('memo', css_class='col-md-6'),
            ),
            'description',
            HTML('<hr class="my-3"><h5 class="card-title mb-3">Debit Entry</h5>'),
            Row(
                Column('debit_account', css_class='col-md-6'),
                Column('debit_amount', css_class='col-md-6'),
            ),
            HTML('<hr class="my-3"><h5 class="card-title mb-3">Credit Entry</h5>'),
            Row(
                Column('credit_account', css_class='col-md-6'),
                Column('credit_amount', css_class='col-md-6'),
            ),
        )

    def clean(self):
        cleaned_data = super().clean()
        debit_amount = cleaned_data.get('debit_amount')
        credit_amount = cleaned_data.get('credit_amount')

        if debit_amount and credit_amount and abs(debit_amount - credit_amount) > 0.01:
            raise ValidationError(_('Debit and credit amounts must be equal.'))

        return cleaned_data


class RecurringJournalEntryForm(forms.ModelForm):
    """Form for creating recurring journal entries."""

    class Meta:
        model = JournalEntry
        fields = ['date', 'description', 'entry_type']

    def __init__(self, organisation, *args, **kwargs):
        self.organisation = organisation
        super().__init__(*args, **kwargs)

        self.helper = FormHelper()
        self.helper.form_tag = False
