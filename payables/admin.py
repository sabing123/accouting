from django.contrib import admin
from payables.models import Vendor, Bill, BillLine, Payment, PaymentLine, PaymentMethod


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ['vendor_number', 'name', 'email', 'status', 'is_active']
    list_filter = ['status', 'is_active']
    search_fields = ['name', 'vendor_number', 'email']
    autocomplete_fields = ['expense_account', 'payable_account']


class BillLineInline(admin.TabularInline):
    model = BillLine
    extra = 1
    autocomplete_fields = ['account', 'department']


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ['bill_number', 'vendor', 'bill_date', 'due_date', 'total', 'status']
    list_filter = ['status', 'bill_date']
    search_fields = ['bill_number', 'vendor__name', 'vendor_invoice_number']
    autocomplete_fields = ['vendor', 'journal_entry']
    inlines = [BillLineInline]
    date_hierarchy = 'bill_date'


class PaymentLineInline(admin.TabularInline):
    model = PaymentLine
    extra = 1
    autocomplete_fields = ['bill']


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['payment_number', 'vendor', 'payment_date', 'amount', 'status']
    list_filter = ['status', 'payment_date']
    search_fields = ['payment_number', 'vendor__name']
    autocomplete_fields = ['vendor', 'payment_method', 'journal_entry']
    inlines = [PaymentLineInline]
    date_hierarchy = 'payment_date'


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'is_default', 'is_active']
    list_filter = ['type', 'is_default', 'is_active']
