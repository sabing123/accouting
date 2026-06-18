from django.urls import path
from payables import views

app_name = 'payables'

urlpatterns = [
    # Vendors
    path('vendors/', views.VendorListView.as_view(), name='vendor-list'),
    path('vendors/create/', views.VendorCreateView.as_view(), name='vendor-create'),
    path('vendors/<uuid:pk>/', views.VendorDetailView.as_view(), name='vendor-detail'),
    path('vendors/<uuid:pk>/edit/', views.VendorUpdateView.as_view(), name='vendor-edit'),
    path('vendors/<uuid:pk>/statement/', views.VendorStatementView.as_view(), name='vendor-statement'),

    # Bills
    path('bills/', views.BillListView.as_view(), name='bill-list'),
    path('bills/create/', views.BillCreateView.as_view(), name='bill-create'),
    path('bills/<uuid:pk>/', views.BillDetailView.as_view(), name='bill-detail'),
    path('bills/<uuid:pk>/post/', views.BillPostView.as_view(), name='bill-post'),
    path('bills/<uuid:pk>/void/', views.BillVoidView.as_view(), name='bill-void'),

    # Payments
    path('payments/', views.PaymentListView.as_view(), name='payment-list'),
    path('payments/create/', views.PaymentCreateView.as_view(), name='payment-create'),
    path('payments/<uuid:pk>/', views.PaymentDetailView.as_view(), name='payment-detail'),
    path('payments/<uuid:pk>/process/', views.PaymentProcessView.as_view(), name='payment-process'),

    # HTMX
    path('htmx/vendors/<uuid:pk>/bills/', views.VendorBillsHTMXView.as_view(), name='vendor-bills-htmx'),
]
