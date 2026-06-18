from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from typing import List, Dict, Optional

from receivables.models import Customer, Invoice, InvoiceLine, Receipt, ReceiptLine, CreditMemo, Product
from ledger.models import Account, JournalEntry
from ledger.services import JournalEntryService
from organisations.models import Organisation


class CustomerService:
    """Service for managing customers."""

    @staticmethod
    def create_customer(organisation: Organisation, name: str, email: str = '', **kwargs) -> Customer:
        """Create a new customer."""
        customer = Customer.objects.create(
            organisation=organisation,
            name=name,
            email=email,
            **kwargs
        )
        return customer

    @staticmethod
    def update_customer(customer: Customer, **kwargs) -> Customer:
        """Update customer details."""
        for field, value in kwargs.items():
            if hasattr(customer, field):
                setattr(customer, field, value)
        customer.save()
        return customer

    @staticmethod
    def deactivate_customer(customer: Customer) -> Customer:
        """Deactivate a customer."""
        customer.is_active = False
        customer.status = Customer.Status.INACTIVE
        customer.save()
        return customer

    @staticmethod
    def get_customer_statement(customer: Customer, as_of=None) -> Dict:
        """Get customer statement with aging."""
        as_of = as_of or timezone.now().date()

        statement = {
            'customer': customer,
            'as_of': as_of,
            'invoices': [],
            'total_due': Decimal('0'),
            'current': Decimal('0'),
            'days_30': Decimal('0'),
            'days_60': Decimal('0'),
            'days_90': Decimal('0'),
            'over_90': Decimal('0'),
        }

        invoices = customer.invoices.filter(
            status__in=['sent', 'partial'],
            balance__gt=0
        ).order_by('due_date')

        for invoice in invoices:
            days_overdue = (as_of - invoice.due_date).days

            statement['invoices'].append({
                'invoice': invoice,
                'days_overdue': max(0, days_overdue),
            })
            statement['total_due'] += invoice.balance

            if days_overdue <= 0:
                statement['current'] += invoice.balance
            elif days_overdue <= 30:
                statement['days_30'] += invoice.balance
            elif days_overdue <= 60:
                statement['days_60'] += invoice.balance
            elif days_overdue <= 90:
                statement['days_90'] += invoice.balance
            else:
                statement['over_90'] += invoice.balance

        return statement


class InvoiceService:
    """Service for managing customer invoices."""

    @staticmethod
    @transaction.atomic
    def create_invoice(
        organisation: Organisation,
        customer: Customer,
        invoice_date,
        lines: List[Dict],
        created_by,
        **kwargs
    ) -> Invoice:
        """Create a new customer invoice."""

        # Auto-calculate due date if not provided
        invoice = Invoice.objects.create(
            organisation=organisation,
            customer=customer,
            invoice_date=invoice_date,
            created_by=created_by,
            **kwargs
        )

        if not invoice.due_date:
            invoice.due_date = invoice.calculate_due_date()

        # Create lines
        subtotal = Decimal('0')
        tax_amount = Decimal('0')

        for idx, line_data in enumerate(lines):
            quantity = Decimal(str(line_data.get('quantity', 1)))
            unit_price = Decimal(str(line_data.get('unit_price', 0)))
            tax_rate = Decimal(str(line_data.get('tax_rate', 0)))
            discount_percent = Decimal(str(line_data.get('discount_percent', 0)))

            base_total = quantity * unit_price
            discount_amount = base_total * (discount_percent / 100)
            line_total = base_total - discount_amount
            line_tax = line_total * (tax_rate / 100)

            InvoiceLine.objects.create(
                invoice=invoice,
                description=line_data.get('description', ''),
                quantity=quantity,
                unit_price=unit_price,
                account_id=line_data.get('account'),
                product_id=line_data.get('product'),
                tax_code=line_data.get('tax_code', ''),
                tax_rate=tax_rate,
                tax_amount=line_tax,
                discount_percent=discount_percent,
                discount_amount=discount_amount,
                line_total=line_total,
                department_id=line_data.get('department'),
                sequence=idx,
            )

            subtotal += line_total
            tax_amount += line_tax

        invoice.subtotal = subtotal
        invoice.tax_amount = tax_amount
        invoice.total = subtotal + tax_amount - invoice.discount_amount + invoice.adjustment
        invoice.balance = invoice.total
        invoice.save()

        return invoice

    @staticmethod
    @transaction.atomic
    def send_invoice(invoice: Invoice, sent_by) -> Invoice:
        """Send invoice and post to accounting."""
        if invoice.status not in [Invoice.Status.DRAFT, Invoice.Status.PENDING]:
            raise ValueError("Only draft or pending invoices can be sent.")

        # Get accounts
        ar_account = invoice.customer.receivable_account or \
            invoice.organisation.accounts.filter(code='1100').first()  # Accounts Receivable

        if not ar_account:
            raise ValueError("No Accounts Receivable account found.")

        # Create journal entry
        lines = []

        # Debit Accounts Receivable
        lines.append({
            'account': ar_account.id,
            'debit': invoice.total,
            'credit': 0,
            'description': f"{invoice.customer.name} - {invoice.invoice_number}",
        })

        # Credit Revenue accounts (from lines)
        for inv_line in invoice.lines.all():
            lines.append({
                'account': inv_line.account_id,
                'debit': 0,
                'credit': inv_line.line_total,
                'description': f"{invoice.customer.name} - {inv_line.description}",
            })

        # Credit tax account if applicable
        if invoice.tax_amount > 0:
            tax_account = invoice.organisation.accounts.filter(
                name__icontains='tax payable'
            ).first() or invoice.organisation.accounts.filter(
                account_type__name='liability',
                name__icontains='tax'
            ).first()

            if tax_account:
                lines.append({
                    'account': tax_account.id,
                    'debit': 0,
                    'credit': invoice.tax_amount,
                    'description': f"Tax on {invoice.invoice_number}",
                })

        journal_entry = JournalEntryService.create_entry(
            organisation=invoice.organisation,
            date=invoice.invoice_date,
            description=f"Invoice {invoice.invoice_number} to {invoice.customer.name}",
            lines=lines,
            created_by=sent_by,
            source_type='invoice',
            source_id=invoice.id,
        )

        JournalEntryService.post_entry(journal_entry, sent_by)

        invoice.status = Invoice.Status.SENT
        invoice.journal_entry = journal_entry
        invoice.sent_by = sent_by
        invoice.sent_date = timezone.now().date()
        invoice.save()

        return invoice

    @staticmethod
    @transaction.atomic
    def cancel_invoice(invoice: Invoice, cancelled_by, reason: str = '') -> Invoice:
        """Cancel a sent invoice."""
        if invoice.status == Invoice.Status.CANCELLED:
            raise ValueError("Invoice is already cancelled.")

        if invoice.status == Invoice.Status.PAID:
            raise ValueError("Cannot cancel a paid invoice.")

        # Void the journal entry
        if invoice.journal_entry:
            invoice.journal_entry.void(cancelled_by, reason)

        invoice.status = Invoice.Status.CANCELLED
        invoice.voided_by = cancelled_by
        invoice.voided_at = timezone.now()
        invoice.void_reason = reason
        invoice.save()

        return invoice

    @staticmethod
    def calculate_totals(invoice: Invoice) -> Invoice:
        """Recalculate invoice totals from lines."""
        subtotal = invoice.lines.aggregate(total=models.Sum('line_total'))['total'] or 0
        tax_amount = invoice.lines.aggregate(tax=models.Sum('tax_amount'))['tax'] or 0

        invoice.subtotal = subtotal
        invoice.tax_amount = tax_amount
        invoice.total = subtotal + tax_amount - invoice.discount_amount + invoice.adjustment

        if invoice.pk:
            paid = invoice.payments.aggregate(total=models.Sum('amount'))['total'] or 0
            invoice.balance = invoice.total - paid
        else:
            invoice.balance = invoice.total

        invoice.save()
        return invoice


class ReceiptService:
    """Service for managing customer receipts."""

    @staticmethod
    @transaction.atomic
    def create_receipt(
        organisation: Organisation,
        customer: Customer,
        receipt_date,
        amount: Decimal,
        applications: List[Dict],
        created_by,
        **kwargs
    ) -> Receipt:
        """Create a customer receipt."""

        receipt = Receipt.objects.create(
            organisation=organisation,
            customer=customer,
            receipt_date=receipt_date,
            amount=amount,
            status=Receipt.Status.DRAFT,
            created_by=created_by,
            **kwargs
        )

        # Create receipt applications
        total_applied = Decimal('0')
        for app_data in applications:
            ReceiptLine.objects.create(
                receipt=receipt,
                invoice_id=app_data['invoice_id'],
                amount=app_data['amount'],
                discount_taken=app_data.get('discount', 0),
            )
            total_applied += Decimal(str(app_data['amount']))

            # Update invoice status
            invoice = Invoice.objects.get(id=app_data['invoice_id'])
            invoice.balance -= Decimal(str(app_data['amount']))

            if invoice.balance <= 0:
                invoice.status = Invoice.Status.PAID
            elif invoice.balance < invoice.total:
                invoice.status = Invoice.Status.PARTIAL

            invoice.save()

        # Handle excess as prepayment/credit
        if total_applied < amount:
            # Create unapplied receipt line
            ReceiptLine.objects.create(
                receipt=receipt,
                invoice=None,
                amount=amount - total_applied,
            )

        return receipt

    @staticmethod
    @transaction.atomic
    def process_receipt(receipt: Receipt, processed_by) -> Receipt:
        """Process (post) a receipt to accounting."""

        if receipt.status != Receipt.Status.DRAFT:
            raise ValueError("Only draft receipts can be processed.")

        # Get accounts
        cash_account = receipt.bank_account.account if receipt.bank_account else \
            receipt.organisation.accounts.filter(is_bank_account=True).first()

        ar_account = receipt.customer.receivable_account or \
            receipt.organisation.accounts.filter(code='1100').first()

        if not cash_account or not ar_account:
            raise ValueError("Required accounts not found.")

        # Create journal entry
        lines = [
            {
                'account': cash_account.id,
                'debit': receipt.amount,
                'credit': 0,
                'description': f"Payment from {receipt.customer.name} - {receipt.receipt_number}",
            },
            {
                'account': ar_account.id,
                'debit': 0,
                'credit': receipt.amount,
                'description': f"Payment from {receipt.customer.name} - {receipt.receipt_number}",
            },
        ]

        journal_entry = JournalEntryService.create_entry(
            organisation=receipt.organisation,
            date=receipt.receipt_date,
            description=f"Receipt {receipt.receipt_number} from {receipt.customer.name}",
            lines=lines,
            created_by=processed_by,
            source_type='receipt',
            source_id=receipt.id,
        )

        JournalEntryService.post_entry(journal_entry, processed_by)

        receipt.status = Receipt.Status.PROCESSED
        receipt.journal_entry = journal_entry
        receipt.processed_by = processed_by
        receipt.processed_at = timezone.now()
        receipt.save()

        return receipt

    @staticmethod
    @transaction.atomic
    def void_receipt(receipt: Receipt, voided_by, reason: str = '') -> Receipt:
        """Void a processed receipt."""

        if receipt.status not in [Receipt.Status.PROCESSED, Receipt.Status.DEPOSITED]:
            raise ValueError("Only processed receipts can be voided.")

        # Void journal entry
        if receipt.journal_entry:
            receipt.journal_entry.void(voided_by, reason)

        # Reverse invoice status changes
        for app in receipt.applications.all():
            if app.invoice:
                invoice = app.invoice
                invoice.balance += app.amount
                if invoice.status == Invoice.Status.PAID:
                    invoice.status = Invoice.Status.SENT
                elif invoice.status == Invoice.Status.PARTIAL and invoice.balance < invoice.total:
                    invoice.status = Invoice.Status.SENT
                invoice.save()

        receipt.status = Receipt.Status.VOIDED
        receipt.voided_by = voided_by
        receipt.voided_at = timezone.now()
        receipt.void_reason = reason
        receipt.save()

        return receipt


class CreditMemoService:
    """Service for managing credit memos."""

    @staticmethod
    @transaction.atomic
    def create_credit_memo(
        organisation: Organisation,
        customer: Customer,
        credit_date,
        amount: Decimal,
        reason: str,
        invoice=None,
        created_by=None,
    ) -> CreditMemo:
        """Create a credit memo."""

        memo = CreditMemo.objects.create(
            organisation=organisation,
            customer=customer,
            credit_date=credit_date,
            amount=amount,
            reason=reason,
            invoice=invoice,
            created_by=created_by,
        )

        return memo

    @staticmethod
    @transaction.atomic
    def issue_credit_memo(memo: CreditMemo, issued_by) -> CreditMemo:
        """Issue credit memo and create journal entry."""

        if memo.status != CreditMemo.Status.DRAFT:
            raise ValueError("Only draft credit memos can be issued.")

        # Get accounts
        ar_account = memo.customer.receivable_account or \
            memo.organisation.accounts.filter(code='1100').first()

        revenue_account = memo.organisation.accounts.filter(
            account_type__name='income'
        ).first()

        if not ar_account or not revenue_account:
            raise ValueError("Required accounts not found.")

        # Create journal entry
        lines = [
            {
                'account': ar_account.id,
                'debit': 0,
                'credit': memo.amount,
                'description': f"Credit memo {memo.credit_number} for {memo.customer.name}",
            },
            {
                'account': revenue_account.id,
                'debit': memo.amount,
                'credit': 0,
                'description': f"Credit memo {memo.credit_number} - {memo.reason}",
            },
        ]

        journal_entry = JournalEntryService.create_entry(
            organisation=memo.organisation,
            date=memo.credit_date,
            description=f"Credit Memo {memo.credit_number}",
            lines=lines,
            created_by=issued_by,
            source_type='credit_memo',
            source_id=memo.id,
        )

        JournalEntryService.post_entry(journal_entry, issued_by)

        memo.status = CreditMemo.Status.ISSUED
        memo.journal_entry = journal_entry
        memo.save()

        return memo

    @staticmethod
    def apply_credit_to_invoice(memo: CreditMemo, invoice: Invoice) -> CreditMemo:
        """Apply credit memo to an invoice."""

        if memo.status != CreditMemo.Status.ISSUED:
            raise ValueError("Only issued credit memos can be applied.")

        if invoice.balance < memo.amount:
            raise ValueError("Credit amount exceeds invoice balance.")

        invoice.balance -= memo.amount

        if invoice.balance <= 0:
            invoice.status = Invoice.Status.PAID
        else:
            invoice.status = Invoice.Status.PARTIAL

        invoice.save()

        memo.invoice = invoice
        memo.status = CreditMemo.Status.APPLIED
        memo.save()

        return memo
