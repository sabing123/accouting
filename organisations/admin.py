from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from organisations.models import Organisation, OrganisationDomain, OrganisationInvitation, OrganisationMembership, Department


@admin.register(Organisation)
class OrganisationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'subscription_status', 'is_active', 'created_at']
    list_filter = ['subscription_status', 'is_active', 'type', 'size']
    search_fields = ['name', 'slug', 'email']
    readonly_fields = ['id', 'slug', 'created_at', 'updated_at']
    ordering = ['-created_at']

    fieldsets = (
        (_('Basic Information'), {
            'fields': ('id', 'name', 'slug', 'legal_name', 'type', 'size', 'industry', 'description')
        }),
        (_('Contact'), {
            'fields': ('email', 'phone', 'website')
        }),
        (_('Address'), {
            'fields': ('address_line1', 'address_line2', 'city', 'state_province', 'postal_code', 'country')
        }),
        (_('Tax & Registration'), {
            'fields': ('tax_id', 'registration_number')
        }),
        (_('Localization'), {
            'fields': ('base_currency', 'timezone', 'date_format', 'fiscal_year_start_month')
        }),
        (_('Subscription'), {
            'fields': ('subscription_status', 'subscription_plan', 'stripe_customer_id', 'stripe_subscription_id', 'trial_ends_at')
        }),
        (_('Organization Structure'), {
            'fields': ('parent',)
        }),
        (_('Branding'), {
            'fields': ('logo', 'primary_color', 'secondary_color')
        }),
        (_('Settings'), {
            'fields': ('settings', 'is_active', 'is_verified')
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(OrganisationDomain)
class OrganisationDomainAdmin(admin.ModelAdmin):
    list_display = ['domain', 'organisation', 'is_primary', 'is_verified']
    list_filter = ['is_primary', 'is_verified']
    search_fields = ['domain', 'organisation__name']
    autocomplete_fields = ['organisation']


@admin.register(OrganisationMembership)
class OrganisationMembershipAdmin(admin.ModelAdmin):
    list_display = ['user', 'organisation', 'role', 'is_default', 'created_at']
    list_filter = ['role', 'is_default']
    search_fields = ['user__email', 'user__first_name', 'organisation__name']
    autocomplete_fields = ['user', 'organisation']


@admin.register(OrganisationInvitation)
class OrganisationInvitationAdmin(admin.ModelAdmin):
    list_display = ['email', 'organisation', 'role', 'status', 'expires_at', 'created_at']
    list_filter = ['status', 'role']
    search_fields = ['email', 'organisation__name']
    autocomplete_fields = ['organisation', 'invited_by']
    readonly_fields = ['token']


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'organisation', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'code', 'organisation__name']
    autocomplete_fields = ['organisation', 'parent', 'manager']
