from rest_framework import viewsets, serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone

from organisations.middleware import get_current_tenant
from ledger.models import Account, JournalEntry, JournalEntryLine, FiscalYear, FiscalPeriod, RecurringJournalEntry
from ledger.services import JournalEntryService, ChartOfAccountsService


class AccountSerializer(serializers.ModelSerializer):
    """Serializer for Account model."""

    class Meta:
        model = Account
        fields = [
            'id', 'code', 'name', 'account_type', 'category',
            'description', 'parent', 'level', 'status', 'is_active',
            'is_header', 'allow_transactions', 'is_bank_account',
            'is_reconcilable', 'currency', 'opening_balance',
            'current_balance', 'period_debit', 'period_credit',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'level', 'current_balance', 'period_debit', 'period_credit', 'created_at', 'updated_at']


class JournalEntryLineSerializer(serializers.ModelSerializer):
    """Serializer for Journal Entry Lines."""

    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = JournalEntryLine
        fields = [
            'id', 'account', 'account_code', 'account_name',
            'debit_amount', 'credit_amount', 'description',
            'department', 'cost_center', 'project',
            'tax_code', 'tax_amount', 'sequence'
        ]


class JournalEntrySerializer(serializers.ModelSerializer):
    """Serializer for Journal Entry model."""

    lines = JournalEntryLineSerializer(many=True, read_only=True)
    total_debit = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)
    total_credit = serializers.DecimalField(max_digits=20, decimal_places=2, read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            'id', 'entry_number', 'reference', 'date', 'fiscal_year',
            'fiscal_period', 'entry_type', 'status', 'description',
            'memo', 'source_type', 'source_id', 'lines',
            'total_debit', 'total_credit', 'currency',
            'created_by', 'posted_by', 'posted_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'entry_number', 'created_at', 'updated_at', 'posted_at']


class JournalEntryCreateSerializer(serializers.Serializer):
    """Serializer for creating journal entries."""

    date = serializers.DateField()
    description = serializers.CharField()
    reference = serializers.CharField(required=False, allow_blank=True)
    entry_type = serializers.ChoiceField(choices=JournalEntry.EntryType.choices, default='general')
    memo = serializers.CharField(required=False, allow_blank=True)

    lines = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False
    )

    # Each line should have: account (uuid), debit (decimal), credit (decimal), description (str)


class AccountViewSet(viewsets.ModelViewSet):
    """API endpoint for accounts."""

    serializer_class = AccountSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        tenant = get_current_tenant()
        if not tenant:
            return Account.objects.none()

        queryset = Account.objects.filter(organisation=tenant).select_related('account_type', 'category', 'parent')

        # Filters
        account_type = self.request.query_params.get('account_type')
        if account_type:
            queryset = queryset.filter(account_type__name=account_type)

        is_active = self.request.query_params.get('is_active')
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')

        is_bank_account = self.request.query_params.get('is_bank_account')
        if is_bank_account is not None:
            queryset = queryset.filter(is_bank_account=is_bank_account.lower() == 'true')

        search = self.request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                models.Q(code__icontains=search) | models.Q(name__icontains=search)
            )

        return queryset.order_by('code')

    @action(detail=True, methods=['get'])
    def activity(self, request, pk=None):
        """Get account activity."""
        account = self.get_object()

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', str(timezone.now().date()))

        if not start_date:
            start_date = str(timezone.now().date().replace(day=1))

        from ledger.services import AccountBalanceService
        activity = AccountBalanceService.get_account_activity(
            account=account,
            start_date=start_date,
            end_date=end_date
        )

        return Response({
            'account': AccountSerializer(account).data,
            'activity': activity,
        })

    @action(detail=True, methods=['post'])
    def update_balance(self, request, pk=None):
        """Force update account balance."""
        account = self.get_object()
        account.update_balance()
        return Response({'status': 'balance updated', 'balance': account.current_balance})


class JournalEntryViewSet(viewsets.ModelViewSet):
    """API endpoint for journal entries."""

    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return JournalEntryCreateSerializer
        return JournalEntrySerializer

    def get_queryset(self):
        tenant = get_current_tenant()
        if not tenant:
            return JournalEntry.objects.none()

        queryset = JournalEntry.objects.filter(
            organisation=tenant
        ).select_related('fiscal_year', 'fiscal_period', 'created_by').prefetch_related('lines__account')

        # Filters
        status = self.request.query_params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        entry_type = self.request.query_params.get('entry_type')
        if entry_type:
            queryset = queryset.filter(entry_type=entry_type)

        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(date__gte=date_from)

        date_to = self.request.query_params.get('date_to')
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        return queryset.order_by('-date', '-created_at')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant = get_current_tenant()
        if not tenant:
            return Response({'error': 'No tenant context'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            entry = JournalEntryService.create_entry(
                organisation=tenant,
                date=serializer.validated_data['date'],
                description=serializer.validated_data['description'],
                lines=serializer.validated_data['lines'],
                created_by=request.user,
                reference=serializer.validated_data.get('reference', ''),
                entry_type=serializer.validated_data.get('entry_type', 'general'),
                memo=serializer.validated_data.get('memo', ''),
            )

            return Response(
                JournalEntrySerializer(entry).data,
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        """Post a journal entry."""
        entry = self.get_object()

        try:
            JournalEntryService.post_entry(entry, request.user)
            return Response({'status': 'posted', 'entry': JournalEntrySerializer(entry).data})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def void(self, request, pk=None):
        """Void a journal entry."""
        entry = self.get_object()
        reason = request.data.get('reason', '')

        try:
            JournalEntryService.void_entry(entry, request.user, reason)
            return Response({'status': 'voided'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
