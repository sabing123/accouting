from django.urls import path
from users import views

app_name = 'users'

urlpatterns = [
    path('profile/', views.UserProfileView.as_view(), name='profile'),
    path('settings/', views.UserSettingsView.as_view(), name='settings'),
    path('activity/', views.UserActivityListView.as_view(), name='activity'),
    path('verify/<str:code>/', views.VerifyEmailView.as_view(), name='verify-email'),
    path('resend-verification/', views.ResendVerificationView.as_view(), name='resend-verification'),

    # HTMX endpoints
    path('htmx/profile/', views.UserProfileView.as_view(), name='profile-htmx'),
]
