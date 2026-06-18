from rest_framework import viewsets, serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from organisations.middleware import get_current_tenant
from receivables.models import Customer, Invoice, Receipt
from receivables.services import CustomerService, InvoiceService, ReceiptService


class CustomerSerializer(serializers.ModelSerializer):
    """Serializer for Customer model."""

    outstanding_balance = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)

    class Meta:
        model = Customer
        fields = [
            'id', 'customer_number', 'name', 'display_name', 'contact_name',
            'email', 'phone', 'status', 'is_active',
            'payment_terms', 'currency', 'credit_limit',
            'tax_id', 'outstanding_balance',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'customer_number', 'outstanding_balance', 'created_at', 'updated_at']


class InvoiceLineSerializer(serializers.ModelSerializer):
    """Serializer for Invoice Lines."""

    account_code = serializers.CharField(source='account.code', read_only=True)

    class Meta:
        model = 'InvoiceLine'
        fields = ['id', 'description', 'quantity', 'unit_price', 'line_total', 'account', 'account_code', 'tax_amount']


class InvoiceSerializer(serializers.ModelSerializer):
    """Serializer for Invoice model."""

    customer_name = serializers.CharField(source='customer.name', read_only=True)
    lines = InvoiceLineSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'quote_number', 'customer', 'customer_name',
            'invoice_date', 'due_date', 'status', 'payment_terms',
            'subtotal', 'tax_amount', 'discount_amount', 'total', 'balance',
            'lines', 'is_overdue', 'days_overdue',
            'currency', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'invoice_number', 'subtotal', 'total', 'balance', 'created_at', 'updated_at']


class ReceiptSerializer(serializers.ModelSerializer):
    """Serializer for Receipt model."""

    customer_name = serializers.CharField(source='customer.name', read_only=True)

    class Meta:
        model = Receipt
        fields = [
            'id', 'receipt_number', 'customer', 'customer_name',
            'receipt_date', 'amount', 'status', 'payment_method',
            'check_number', 'reference', 'memo',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'receipt_number', 'created_at', 'updated_at']


class CustomerViewSet(viewsets.ModelViewSet):
    """API endpoint for customers."""

    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_current_tenant()
        if not tenant:
            return Customer.objects.none()

        queryset = Customer.objects.filter(organisation=tenant)

        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by('name')

    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):
        """Get customer statement."""
        customer = self.get_object()
        statement = CustomerService.get_customer_statement(customer)
        return Response(statement)


class InvoiceViewSet(viewsets.ModelViewSet):
    """API endpoint for invoices."""

    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_current_tenant()
        if not tenant:
            return Invoice.objects.none()

        queryset = Invoice.objects.filter(organisation=tenant).select_related('customer').prefetch_related('lines')

        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        customer = self.request.query_params.get('customer')
        if customer:
            queryset = queryset.filter(customer_id=customer)

        return queryset.order_by('-invoice_date')

    @action(detail=True, methods=['post'])
    def send(self, request, pk=None):
        """Send an invoice."""
        invoice = self.get_object()

        try:
            InvoiceService.send_invoice(invoice, request.user)
            return Response({'status': 'sent'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ReceiptViewSet(viewsets.ModelViewSet):
    """API endpoint for receipts."""

    serializer_class = ReceiptSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_current_tenant()
        if not tenant:
            return Receipt.objects.none()

        queryset = Receipt.objects.filter(organisation=tenant).select_related('customer')

        customer = self.request.query_params.get('customer')
        if customer:
            queryset = queryset.filter(customer_id=customer)

        return queryset.order_by('-receipt_date')
