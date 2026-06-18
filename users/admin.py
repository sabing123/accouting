from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from users.models import User, UserProfile, UserActivity


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'first_name', 'last_name', 'is_staff', 'is_active', 'email_verified', 'created_at']
    list_filter = ['is_staff', 'is_active', 'email_verified', 'two_factor_enabled']
    search_fields = ['email', 'first_name', 'last_name']
    ordering = ['email']
    readonly_fields = ['id', 'created_at', 'updated_at', 'last_login']

    fieldsets = (
        (None, {'fields': ('id', 'email', 'password')}),
        (_('Personal Info'), {
            'fields': ('first_name', 'last_name', 'job_title', 'phone', 'avatar')
        }),
        (_('Preferences'), {
            'fields': ('timezone', 'language', 'date_format', 'email_notifications', 'weekly_report')
        }),
        (_('Security'), {
            'fields': ('two_factor_enabled', 'two_factor_secret', 'last_login_ip', 'password_changed_at'),
            'classes': ('collapse',)
        }),
        (_('Email Verification'), {
            'fields': ('email_verified', 'verification_code', 'verification_code_expires'),
            'classes': ('collapse',)
        }),
        (_('Permissions'), {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
        (_('Important dates'), {
            'fields': ('last_login', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'password1', 'password2'),
        }),
    )

    filter_horizontal = ('groups', 'user_permissions')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'city', 'country', 'created_at']
    search_fields = ['user__email', 'user__first_name', 'user__last_name', 'city', 'country']
    list_filter = ['country']


@admin.register(UserActivity)
class UserActivityAdmin(admin.ModelAdmin):
    list_display = ['user', 'action', 'ip_address', 'created_at']
    list_filter = ['action', 'created_at']
    search_fields = ['user__email', 'ip_address']
    readonly_fields = ['user', 'action', 'ip_address', 'user_agent', 'metadata', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# Unregister the default Group model
from django.contrib.auth.models import Group
admin.site.unregister(Group)
