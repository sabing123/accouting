from django.urls import path
from receivables import views

app_name = 'receivables'

urlpatterns = [
    # Customers
    path('customers/', views.CustomerListView.as_view(), name='customer-list'),
    path('customers/create/', views.CustomerCreateView.as_view(), name='customer-create'),
    path('customers/<uuid:pk>/', views.CustomerDetailView.as_view(), name='customer-detail'),
    path('customers/<uuid:pk>/edit/', views.CustomerUpdateView.as_view(), name='customer-edit'),
    path('customers/<uuid:pk>/statement/', views.CustomerStatementView.as_view(), name='customer-statement'),

    # Products
    path('products/', views.ProductListView.as_view(), name='product-list'),
    path('products/create/', views.ProductCreateView.as_view(), name='product-create'),
    path('products/<uuid:pk>/edit/', views.ProductUpdateView.as_view(), name='product-edit'),

    # Invoices
    path('invoices/', views.InvoiceListView.as_view(), name='invoice-list'),
    path('invoices/create/', views.InvoiceCreateView.as_view(), name='invoice-create'),
    path('invoices/<uuid:pk>/', views.InvoiceDetailView.as_view(), name='invoice-detail'),
    path('invoices/<uuid:pk>/edit/', views.InvoiceEditView.as_view(), name='invoice-edit'),
    path('invoices/<uuid:pk>/send/', views.InvoiceSendView.as_view(), name='invoice-send'),
    path('invoices/<uuid:pk>/cancel/', views.InvoiceCancelView.as_view(), name='invoice-cancel'),
    path('invoices/<uuid:pk>/pdf/', views.InvoicePDFView.as_view(), name='invoice-pdf'),

    # Receipts
    path('receipts/', views.ReceiptListView.as_view(), name='receipt-list'),
    path('receipts/create/', views.ReceiptCreateView.as_view(), name='receipt-create'),
    path('receipts/<uuid:pk>/', views.ReceiptDetailView.as_view(), name='receipt-detail'),
    path('receipts/<uuid:pk>/process/', views.ReceiptProcessView.as_view(), name='receipt-process'),

    # Credit Memos
    path('credit-memos/', views.CreditMemoListView.as_view(), name='credit-memo-list'),
    path('credit-memos/create/', views.CreditMemoCreateView.as_view(), name='credit-memo-create'),
    path('credit-memos/<uuid:pk>/issue/', views.CreditMemoIssueView.as_view(), name='credit-memo-issue'),

    # HTMX endpoints
    path('htmx/customers/<uuid:pk>/invoices/', views.CustomerInvoicesHTMXView.as_view(), name='customer-invoices-htmx'),
]
