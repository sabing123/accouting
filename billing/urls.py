from django.urls import path
from billing import views

app_name = 'billing'

urlpatterns = [
    path('', views.BillingIndexView.as_view(), name='index'),
    path('plans/', views.PlansListView.as_view(), name='plans'),
    path('subscription/', views.SubscriptionView.as_view(), name='subscription'),
    path('checkout/', views.CheckoutView.as_view(), name='checkout'),
    path('subscription/cancel/', views.CancelSubscriptionView.as_view(), name='cancel'),
    path('subscription/reactivate/', views.ReactivateSubscriptionView.as_view(), name='reactivate'),
    path('subscription/change-plan/', views.ChangePlanView.as_view(), name='change-plan'),
    path('payment-history/', views.PaymentHistoryView.as_view(), name='payment-history'),
    path('create-portal/', views.CreateCustomerPortalView.as_view(), name='create-portal'),
    path('webhook/', views.StripeWebhookView.as_view(), name='webhook'),
]
