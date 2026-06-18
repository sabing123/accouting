from django.contrib import admin
from billing.models import Plan, Subscription, PaymentHistory, Coupon


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'price_monthly', 'price_yearly', 'is_active', 'is_default']
    list_filter = ['is_active', 'is_default']
    search_fields = ['name', 'code']
    ordering = ['sort_order', 'price_monthly']


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ['organisation', 'plan', 'status', 'billing_period', 'current_period_end']
    list_filter = ['status', 'billing_period']
    search_fields = ['organisation__name']
    autocomplete_fields = ['organisation', 'plan']


@admin.register(PaymentHistory)
class PaymentHistoryAdmin(admin.ModelAdmin):
    list_display = ['organisation', 'amount', 'status', 'paid_at', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['organisation__name', 'stripe_invoice_id']
    autocomplete_fields = ['organisation', 'subscription']
    readonly_fields = ['stripe_invoice_id', 'stripe_charge_id', 'stripe_payment_intent_id']

    def has_add_permission(self, request):
        return False


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ['code', 'discount_type', 'discount_value', 'is_active', 'valid_until', 'redemptions_count']
    list_filter = ['discount_type', 'is_active']
    search_fields = ['code']
