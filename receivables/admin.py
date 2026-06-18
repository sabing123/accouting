from django.contrib import admin
from receivables.models import Customer, Product, Invoice, InvoiceLine, Receipt, ReceiptLine, CreditMemo, RecurringInvoice


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['customer_number', 'name', 'email', 'status', 'is_active']
    list_filter = ['status', 'is_active']
    search_fields = ['name', 'customer_number', 'email']
    autocomplete_fields = ['receivable_account', 'revenue_account']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['product_code', 'name', 'type', 'unit_price', 'is_active']
    list_filter = ['type', 'is_active', 'is_taxable']
    search_fields = ['name', 'product_code']
    autocomplete_fields = ['revenue_account', 'cost_account']


class InvoiceLineInline(admin.TabularInline):
    model = InvoiceLine
    extra = 1
    autocomplete_fields = ['account', 'product', 'department']


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'customer', 'invoice_date', 'due_date', 'total', 'status']
    list_filter = ['status', 'invoice_date']
    search_fields = ['invoice_number', 'customer__name']
    autocomplete_fields = ['customer', 'journal_entry']
    inlines = [InvoiceLineInline]
    date_hierarchy = 'invoice_date'


class ReceiptLineInline(admin.TabularInline):
    model = ReceiptLine
    extra = 1
    autocomplete_fields = ['invoice']


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'customer', 'receipt_date', 'amount', 'status']
    list_filter = ['status', 'payment_method', 'receipt_date']
    search_fields = ['receipt_number', 'customer__name', 'check_number']
    autocomplete_fields = ['customer', 'journal_entry', 'bank_account']
    inlines = [ReceiptLineInline]
    date_hierarchy = 'receipt_date'


@admin.register(CreditMemo)
class CreditMemoAdmin(admin.ModelAdmin):
    list_display = ['credit_number', 'customer', 'credit_date', 'amount', 'status']
    list_filter = ['status', 'credit_date']
    search_fields = ['credit_number', 'customer__name']
    autocomplete_fields = ['customer', 'invoice', 'journal_entry']


@admin.register(RecurringInvoice)
class RecurringInvoiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'customer', 'frequency', 'is_active', 'next_run_date']
    list_filter = ['frequency', 'is_active']
    search_fields = ['name', 'customer__name']
    autocomplete_fields = ['customer', 'created_by']
