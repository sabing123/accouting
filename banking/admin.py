from django.contrib import admin
from banking.models import BankAccount, BankTransaction, BankTransactionImport, BankReconciliation, ReconciledLine, Transfer


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'bank_name', 'account_number', 'currency', 'current_balance', 'status']
    list_filter = ['status', 'is_active', 'currency']
    search_fields = ['name', 'bank_name', 'account_number']
    autocomplete_fields = ['account']


class BankTransactionInline(admin.TabularInline):
    model = BankTransaction
    extra = 1
    fields = ['transaction_date', 'amount', 'transaction_type', 'description', 'status']


@admin.register(BankTransactionImport)
class BankTransactionImportAdmin(admin.ModelAdmin):
    list_display = ['filename', 'bank_account', 'status', 'total_transactions', 'created_at']
    list_filter = ['status']
    autocomplete_fields = ['bank_account', 'imported_by']
    inlines = [BankTransactionInline]


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ['transaction_date', 'bank_account', 'amount', 'transaction_type', 'status', 'description']
    list_filter = ['status', 'transaction_type', 'transaction_date']
    search_fields = ['description', 'reference', 'bank_reference']
    autocomplete_fields = ['bank_account', 'matched_journal_line', 'import_batch']
    date_hierarchy = 'transaction_date'


class ReconciledLineInline(admin.TabularInline):
    model = ReconciledLine
    extra = 0
    autocomplete_fields = ['journal_line', 'bank_transaction']


@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ['bank_account', 'statement_date', 'statement_balance', 'book_balance', 'difference', 'status']
    list_filter = ['status']
    autocomplete_fields = ['bank_account', 'reconciled_by']
    inlines = [ReconciledLineInline]


@admin.register(Transfer)
class TransferAdmin(admin.ModelAdmin):
    list_display = ['transfer_number', 'transfer_date', 'amount', 'from_account', 'to_account', 'status']
    list_filter = ['status', 'transfer_date']
    autocomplete_fields = ['from_account', 'to_account', 'journal_entry', 'created_by', 'processed_by']
