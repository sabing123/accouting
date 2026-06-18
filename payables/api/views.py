from rest_framework import viewsets, serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from organisations.middleware import get_current_tenant
from payables.models import Vendor, Bill, Payment
from payables.services import VendorService, BillService, PaymentService


class VendorSerializer(serializers.ModelSerializer):
    """Serializer for Vendor model."""

    outstanding_balance = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)

    class Meta:
        model = Vendor
        fields = [
            'id', 'vendor_number', 'name', 'display_name', 'contact_name',
            'email', 'phone', 'website', 'status', 'is_active',
            'payment_terms', 'currency', 'credit_limit',
            'tax_id', 'tax_code', 'outstanding_balance',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'vendor_number', 'outstanding_balance', 'created_at', 'updated_at']


class BillLineSerializer(serializers.ModelSerializer):
    """Serializer for Bill Lines."""

    account_code = serializers.CharField(source='account.code', read_only=True)

    class Meta:
        model = 'BillLine'
        fields = ['id', 'description', 'quantity', 'unit_price', 'line_total', 'account', 'account_code', 'tax_amount']


class BillSerializer(serializers.ModelSerializer):
    """Serializer for Bill model."""

    vendor_name = serializers.CharField(source='vendor.name', read_only=True)
    lines = BillLineSerializer(many=True, read_only=True)

    class Meta:
        model = Bill
        fields = [
            'id', 'bill_number', 'vendor_invoice_number', 'vendor', 'vendor_name',
            'bill_date', 'due_date', 'status', 'description',
            'subtotal', 'tax_amount', 'discount_amount', 'total', 'balance',
            'lines', 'is_overdue', 'days_overdue',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'bill_number', 'subtotal', 'total', 'balance', 'created_at', 'updated_at']


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment model."""

    vendor_name = serializers.CharField(source='vendor.name', read_only=True)

    class Meta:
        model = Payment
        fields = [
            'id', 'payment_number', 'vendor', 'vendor_name',
            'payment_date', 'amount', 'status', 'payment_method',
            'check_number', 'reference', 'memo',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'payment_number', 'created_at', 'updated_at']


class VendorViewSet(viewsets.ModelViewSet):
    """API endpoint for vendors."""

    serializer_class = VendorSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_current_tenant()
        if not tenant:
            return Vendor.objects.none()

        queryset = Vendor.objects.filter(organisation=tenant)

        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset.order_by('name')

    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):
        """Get vendor statement."""
        vendor = self.get_object()
        statement = VendorService.get_vendor_statement(vendor)
        return Response(statement)


class BillViewSet(viewsets.ModelViewSet):
    """API endpoint for bills."""

    serializer_class = BillSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_current_tenant()
        if not tenant:
            return Bill.objects.none()

        queryset = Bill.objects.filter(organisation=tenant).select_related('vendor').prefetch_related('lines')

        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        vendor = self.request.query_params.get('vendor')
        if vendor:
            queryset = queryset.filter(vendor_id=vendor)

        overdue = self.request.query_params.get('overdue')
        if overdue:
            from django.utils import timezone
            queryset = queryset.filter(
                status__in=['open', 'partial'],
                due_date__lt=timezone.now().date()
            )

        return queryset.order_by('-bill_date')

    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        """Post a bill."""
        bill = self.get_object()

        try:
            BillService.post_bill(bill, request.user)
            return Response({'status': 'posted'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PaymentViewSet(viewsets.ModelViewSet):
    """API endpoint for payments."""

    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_current_tenant()
        if not tenant:
            return Payment.objects.none()

        queryset = Payment.objects.filter(organisation=tenant).select_related('vendor', 'payment_method')

        vendor = self.request.query_params.get('vendor')
        if vendor:
            queryset = queryset.filter(vendor_id=vendor)

        return queryset.order_by('-payment_date')
