from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from typing import List, Dict, Optional

from payables.models import Vendor, Bill, BillLine, Payment, PaymentLine, PaymentMethod
from ledger.models import Account, JournalEntry, JournalEntryLine
from ledger.services import JournalEntryService
from organisations.models import Organisation


class VendorService:
    """Service for managing vendors."""

    @staticmethod
    def create_vendor(
        organisation: Organisation,
        name: str,
        email: str = '',
        **kwargs
    ) -> Vendor:
        """Create a new vendor."""
        vendor = Vendor.objects.create(
            organisation=organisation,
            name=name,
            email=email,
            **kwargs
        )
        return vendor

    @staticmethod
    def update_vendor(vendor: Vendor, **kwargs) -> Vendor:
        """Update vendor details."""
        for field, value in kwargs.items():
            if hasattr(vendor, field):
                setattr(vendor, field, value)
        vendor.save()
        return vendor

    @staticmethod
    def deactivate_vendor(vendor: Vendor) -> Vendor:
        """Deactivate a vendor."""
        vendor.is_active = False
        vendor.status = Vendor.Status.INACTIVE
        vendor.save()
        return vendor

    @staticmethod
    def put_on_hold(vendor: Vendor, reason: str = '') -> Vendor:
        """Put vendor on hold."""
        vendor.status = Vendor.Status.ON_HOLD
        vendor.hold_reason = reason
        vendor.save()
        return vendor

    @staticmethod
    def release_hold(vendor: Vendor) -> Vendor:
        """Release vendor from hold."""
        vendor.status = Vendor.Status.ACTIVE
        vendor.hold_reason = ''
        vendor.save()
        return vendor

    @staticmethod
    def get_vendor_statement(vendor: Vendor, as_of=None) -> Dict:
        """Get vendor statement with all open bills."""
        as_of = as_of or timezone.now().date()

        statement = {
            'vendor': vendor,
            'as_of': as_of,
            'bills': [],
            'total_due': Decimal('0'),
            'current': Decimal('0'),
            'days_30': Decimal('0'),
            'days_60': Decimal('0'),
            'days_90': Decimal('0'),
            'over_90': Decimal('0'),
        }

        bills = vendor.bills.filter(
            status__in=['open', 'partial'],
            balance__gt=0
        ).order_by('due_date')

        for bill in bills:
            days_overdue = (as_of - bill.due_date).days

            statement['bills'].append({
                'bill': bill,
                'days_overdue': max(0, days_overdue),
            })
            statement['total_due'] += bill.balance

            if days_overdue <= 0:
                statement['current'] += bill.balance
            elif days_overdue <= 30:
                statement['days_30'] += bill.balance
            elif days_overdue <= 60:
                statement['days_60'] += bill.balance
            elif days_overdue <= 90:
                statement['days_90'] += bill.balance
            else:
                statement['over_90'] += bill.balance

        return statement


class BillService:
    """Service for managing vendor bills."""

    @staticmethod
    @transaction.atomic
    def create_bill(
        organisation: Organisation,
        vendor: Vendor,
        bill_date,
        due_date,
        lines: List[Dict],
        created_by,
        **kwargs
    ) -> Bill:
        """Create a new vendor bill."""

        # Calculate totals
        subtotal = Decimal('0')
        tax_amount = Decimal('0')
        bill_lines = []

        for idx, line_data in enumerate(lines):
            line_total = Decimal(str(line_data.get('quantity', 1))) * Decimal(str(line_data.get('unit_price', 0)))
            line_tax = line_total * (Decimal(str(line_data.get('tax_rate', 0))) / 100)

            subtotal += line_total
            tax_amount += line_tax

            bill_lines.append({
                'sequence': idx,
                'description': line_data.get('description', ''),
                'quantity': line_data.get('quantity', 1),
                'unit_price': line_data.get('unit_price', 0),
                'account_id': line_data.get('account'),
                'tax_code': line_data.get('tax_code', ''),
                'tax_rate': line_data.get('tax_rate', 0),
                'tax_amount': line_tax,
                'line_total': line_total,
                'department_id': line_data.get('department'),
                'cost_center': line_data.get('cost_center', ''),
                'project': line_data.get('project', ''),
            })

        bill = Bill.objects.create(
            organisation=organisation,
            vendor=vendor,
            bill_date=bill_date,
            due_date=due_date,
            subtotal=subtotal,
            tax_amount=tax_amount,
            status=Bill.Status.DRAFT,
            created_by=created_by,
            **kwargs
        )

        # Create lines
        for line_data in bill_lines:
            BillLine.objects.create(
                bill=bill,
                description=line_data['description'],
                quantity=line_data['quantity'],
                unit_price=line_data['unit_price'],
                account_id=line_data['account_id'],
                tax_code=line_data['tax_code'],
                tax_rate=line_data['tax_rate'],
                tax_amount=line_data['tax_amount'],
                line_total=line_data['line_total'],
                department_id=line_data.get('department_id'),
                cost_center=line_data.get('cost_center', ''),
                project=line_data.get('project', ''),
                sequence=line_data['sequence'],
            )

        # Update balance
        bill.balance = bill.total
        bill.save()

        return bill

    @staticmethod
    @transaction.atomic
    def post_bill(bill: Bill, posted_by) -> Bill:
        """Post the bill and create journal entry."""

        if bill.status not in [Bill.Status.DRAFT, Bill.Status.PENDING]:
            raise ValueError("Only draft or pending bills can be posted.")

        # Get the AP account
        ap_account = bill.vendor.payable_account or bill.organisation.accounts.filter(
            code='2000'  # Accounts Payable
        ).first()

        if not ap_account:
            raise ValueError("No Accounts Payable account found.")

        # Create journal entry
        lines = []

        # Debit expense accounts (from lines)
        for bill_line in bill.lines.all():
            lines.append({
                'account': bill_line.account_id,
                'debit': bill_line.line_total,
                'credit': 0,
                'description': f"{bill.vendor.name} - {bill_line.description}",
                'department_id': str(bill_line.department_id) if bill_line.department_id else None,
                'cost_center': bill_line.cost_center,
                'project': bill_line.project,
            })

        # Credit Accounts Payable
        lines.append({
            'account': ap_account.id,
            'debit': 0,
            'credit': bill.total,
            'description': f"{bill.vendor.name} - {bill.bill_number}",
        })

        journal_entry = JournalEntryService.create_entry(
            organisation=bill.organisation,
            date=bill.bill_date,
            description=f"Bill {bill.bill_number} from {bill.vendor.name}",
            lines=lines,
            created_by=posted_by,
            source_type='bill',
            source_id=bill.id,
        )

        JournalEntryService.post_entry(journal_entry, posted_by)

        bill.status = Bill.Status.OPEN
        bill.journal_entry = journal_entry
        bill.posted_by = posted_by
        bill.posted_at = timezone.now()
        bill.save()

        return bill

    @staticmethod
    @transaction.atomic
    def void_bill(bill: Bill, voided_by, reason: str = '') -> Bill:
        """Void a posted bill."""

        if bill.status == Bill.Status.VOIDED:
            raise ValueError("Bill is already voided.")

        if bill.status == Bill.Status.PAID:
            raise ValueError("Cannot void a fully paid bill.")

        # Void the journal entry
        if bill.journal_entry:
            bill.journal_entry.void(voided_by, reason)

        bill.status = Bill.Status.VOIDED
        bill.voided_by = voided_by
        bill.voided_at = timezone.now()
        bill.void_reason = reason
        bill.save()

        return bill

    @staticmethod
    def approve_bill(bill: Bill, approved_by) -> Bill:
        """Approve a bill for payment."""
        if bill.status != Bill.Status.PENDING:
            raise ValueError("Only pending bills can be approved.")

        bill.status = Bill.Status.OPEN
        bill.approved_by = approved_by
        bill.approved_at = timezone.now()
        bill.save()

        return bill


class PaymentService:
    """Service for managing vendor payments."""

    @staticmethod
    @transaction.atomic
    def create_payment(
        organisation: Organisation,
        vendor: Vendor,
        payment_date,
        amount: Decimal,
        payment_method: PaymentMethod,
        applications: List[Dict],
        created_by,
        **kwargs
    ) -> Payment:
        """Create a vendor payment."""

        payment = Payment.objects.create(
            organisation=organisation,
            vendor=vendor,
            payment_date=payment_date,
            amount=amount,
            payment_method=payment_method,
            status=Payment.Status.DRAFT,
            created_by=created_by,
            **kwargs
        )

        # Create payment applications
        total_applied = Decimal('0')
        for app_data in applications:
            PaymentLine.objects.create(
                payment=payment,
                bill_id=app_data['bill_id'],
                amount=app_data['amount'],
                discount_taken=app_data.get('discount', 0),
            )
            total_applied += Decimal(str(app_data['amount']))

            # Update bill status
            bill = Bill.objects.get(id=app_data['bill_id'])
            bill.balance -= Decimal(str(app_data['amount']))

            if bill.balance <= 0:
                bill.status = Bill.Status.PAID
            elif bill.balance < bill.total:
                bill.status = Bill.Status.PARTIAL

            bill.save()

        # Handle unapplied amount (prepayment)
        if total_applied < amount:
            PaymentLine.objects.create(
                payment=payment,
                bill=None,
                amount=amount - total_applied,
            )

        return payment

    @staticmethod
    @transaction.atomic
    def process_payment(payment: Payment, processed_by) -> Payment:
        """Process (post) a payment."""

        if payment.status not in [Payment.Status.DRAFT, Payment.Status.APPROVED]:
            raise ValueError("Only draft or approved payments can be processed.")

        # Get accounts
        cash_account = payment.bank_account.account if payment.bank_account else \
            payment.organisation.accounts.filter(is_bank_account=True).first()

        ap_account = payment.vendor.payable_account or \
            payment.organisation.accounts.filter(code='2000').first()

        if not cash_account or not ap_account:
            raise ValueError("Required accounts not found.")

        # Create journal entry
        lines = [
            {
                'account': ap_account.id,
                'debit': payment.amount,
                'credit': 0,
                'description': f"Payment to {payment.vendor.name} - {payment.payment_number}",
            },
            {
                'account': cash_account.id,
                'debit': 0,
                'credit': payment.amount,
                'description': f"Payment to {payment.vendor.name} - {payment.payment_number}",
            },
        ]

        journal_entry = JournalEntryService.create_entry(
            organisation=payment.organisation,
            date=payment.payment_date,
            description=f"Payment {payment.payment_number} to {payment.vendor.name}",
            lines=lines,
            created_by=processed_by,
            source_type='payment',
            source_id=payment.id,
        )

        JournalEntryService.post_entry(journal_entry, processed_by)

        payment.status = Payment.Status.PROCESSED
        payment.journal_entry = journal_entry
        payment.processed_by = processed_by
        payment.processed_at = timezone.now()
        payment.save()

        return payment

    @staticmethod
    @transaction.atomic
    def void_payment(payment: Payment, voided_by, reason: str = '') -> Payment:
        """Void a processed payment."""

        if payment.status != Payment.Status.PROCESSED:
            raise ValueError("Only processed payments can be voided.")

        # Void journal entry
        if payment.journal_entry:
            payment.journal_entry.void(voided_by, reason)

        # Reverse bill status changes
        for app in payment.applications.all():
            if app.bill:
                bill = app.bill
                bill.balance += app.amount
                if bill.status == Bill.Status.PAID:
                    bill.status = Bill.Status.OPEN
                elif bill.status == Bill.Status.PARTIAL and bill.balance < bill.total:
                    bill.status = Bill.Status.OPEN
                bill.save()

        payment.status = Payment.Status.VOIDED
        payment.voided_by = voided_by
        payment.voided_at = timezone.now()
        payment.void_reason = reason
        payment.save()

        return payment
