from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from typing import List, Dict, Optional
import csv
import io
from datetime import datetime

from banking.models import BankAccount, BankTransaction, BankTransactionImport, BankReconciliation, ReconciledLine, Transfer
from ledger.models import JournalEntry, JournalEntryLine
from ledger.services import JournalEntryService


class BankAccountService:
    """Service for managing bank accounts."""

    @staticmethod
    def create_bank_account(
        organisation,
        name: str,
        bank_name: str,
        account_number: str,
        gl_account,
        **kwargs
    ) -> BankAccount:
        """Create a new bank account."""
        bank_account = BankAccount.objects.create(
            organisation=organisation,
            name=name,
            bank_name=bank_name,
            account_number=account_number,
            account=gl_account,
            **kwargs
        )

        # Mark the GL account as a bank account
        gl_account.is_bank_account = True
        gl_account.is_reconcilable = True
        gl_account.save()

        return bank_account

    @staticmethod
    def update_balance(bank_account: BankAccount) -> BankAccount:
        """Update the bank account balance from transactions."""
        bank_account.update_balance()
        return bank_account


class BankTransactionImportService:
    """Service for importing bank transactions."""

    @staticmethod
    @transaction.atomic
    def import_from_csv(bank_account: BankAccount, csv_file, imported_by, **kwargs) -> BankTransactionImport:
        """Import bank transactions from a CSV file."""

        # Create import record
        import_record = BankTransactionImport.objects.create(
            bank_account=bank_account,
            filename=csv_file.name if hasattr(csv_file, 'name') else 'import.csv',
            imported_by=imported_by,
            status=BankTransactionImport.Status.PROCESSING,
            **kwargs
        )

        try:
            # Parse CSV
            decoded_file = csv_file.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(decoded_file))

            transactions = []
            total_debit = Decimal('0')
            total_credit = Decimal('0')
            min_date = None
            max_date = None
            statement_balance = Decimal('0')

            for row in reader:
                # Parse date (assume standard format)
                date_str = row.get('date', row.get('Date', ''))
                transaction_date = datetime.strptime(date_str, '%Y-%m-%d').date()

                # Parse amount
                amount = Decimal(str(row.get('amount', row.get('Amount', '0'))))

                # Determine type
                if amount < 0:
                    transaction_type = BankTransaction.TransactionType.DEBIT
                    amount = abs(amount)
                    total_debit += amount
                else:
                    transaction_type = BankTransaction.TransactionType.CREDIT
                    total_credit += amount

                # Track date range
                if min_date is None or transaction_date < min_date:
                    min_date = transaction_date
                if max_date is None or transaction_date > max_date:
                    max_date = transaction_date

                # Create transaction
                transaction = BankTransaction(
                    bank_account=bank_account,
                    transaction_date=transaction_date,
                    amount=amount,
                    transaction_type=transaction_type,
                    description=row.get('description', row.get('Description', '')),
                    reference=row.get('reference', row.get('Reference', '')),
                    bank_reference=row.get('bank_reference', row.get('BankReference', '')),
                    import_batch=import_record,
                )
                transactions.append(transaction)

            # Bulk create transactions
            BankTransaction.objects.bulk_create(transactions)

            # Update import record
            import_record.total_transactions = len(transactions)
            import_record.total_debit = total_debit
            import_record.total_credit = total_credit
            import_record.statement_from_date = min_date
            import_record.statement_to_date = max_date
            import_record.status = BankTransactionImport.Status.COMPLETED
            import_record.processed_at = timezone.now()
            import_record.save()

        except Exception as e:
            import_record.status = BankTransactionImport.Status.FAILED
            import_record.error_message = str(e)
            import_record.save()

        return import_record

    @staticmethod
    def auto_match_transactions(bank_account: BankAccount):
        """Automatically match imported transactions with journal entries."""

        unmatched = BankTransaction.objects.filter(
            bank_account=bank_account,
            status=BankTransaction.Status.UNMATCHED
        )

        for bank_trans in unmatched:
            # Look for matching journal entry lines
            potential_matches = JournalEntryLine.objects.filter(
                account=bank_account.account,
                entry__status=JournalEntry.Status.POSTED,
                entry__date=bank_trans.transaction_date,
            ).exclude(
                reconciliations__journal_line__isnull=False  # Already reconciled
            )

            if bank_trans.is_debit:
                # Look for debit entries
                potential_matches = potential_matches.filter(debit_amount=bank_trans.amount)
            else:
                # Look for credit entries
                potential_matches = potential_matches.filter(credit_amount=bank_trans.amount)

            # Auto-match if exactly one match found
            if potential_matches.count() == 1:
                matched_line = potential_matches.first()
                bank_trans.matched_journal_line = matched_line
                bank_trans.status = BankTransaction.Status.MATCHED
                bank_trans.save()


class ReconciliationService:
    """Service for bank reconciliation."""

    @staticmethod
    @transaction.atomic
    def start_reconciliation(
        bank_account: BankAccount,
        statement_date,
        statement_balance: Decimal,
        reconciled_by,
    ) -> BankReconciliation:
        """Start a new bank reconciliation."""

        # Get book balance
        bank_account.update_balance()

        reconciliation = BankReconciliation.objects.create(
            bank_account=bank_account,
            statement_date=statement_date,
            statement_balance=statement_balance,
            book_balance=bank_account.current_balance,
        )

        # Calculate and set adjusted balance
        reconciliation.calculate_difference()
        reconciliation.save()

        return reconciliation

    @staticmethod
    @transaction.atomic
    def reconcile_line(
        reconciliation: BankReconciliation,
        journal_line: JournalEntryLine,
        bank_transaction: Optional[BankTransaction] = None,
    ) -> ReconciledLine:
        """Reconcile a journal line with or without a bank transaction."""

        reconciled_line = ReconciledLine.objects.create(
            reconciliation=reconciliation,
            journal_line=journal_line,
            bank_transaction=bank_transaction,
        )

        # Mark journal line as reconciled
        journal_line.reconciled = True
        journal_line.reconciled_date = reconciliation.statement_date
        journal_line.save()

        # Mark bank transaction as reconciled
        if bank_transaction:
            bank_transaction.status = BankTransaction.Status.RECONCILED
            bank_transaction.save()

        return reconciled_line

    @staticmethod
    def calculate_adjustments(reconciliation: BankReconciliation) -> Dict:
        """Calculate deposits in transit and outstanding checks."""

        # Deposits in transit = checks received but not yet cleared
        deposits = JournalEntryLine.objects.filter(
            account=reconciliation.bank_account.account,
            credit_amount__gt=0,
            reconciled=False,
            entry__status=JournalEntry.Status.POSTED,
            entry__date__lte=reconciliation.statement_date,
        ).aggregate(total=models.Sum('credit_amount'))['total'] or Decimal('0')

        # Outstanding checks = checks written but not yet cleared
        checks = JournalEntryLine.objects.filter(
            account=reconciliation.bank_account.account,
            debit_amount__gt=0,
            reconciled=False,
            entry__status=JournalEntry.Status.POSTED,
            entry__date__lte=reconciliation.statement_date,
        ).aggregate(total=models.Sum('debit_amount'))['total'] or Decimal('0')

        reconciliation.deposits_in_transit = deposits
        reconciliation.outstanding_checks = checks
        reconciliation.calculate_difference()
        reconciliation.save()

        return {
            'deposits_in_transit': deposits,
            'outstanding_checks': checks,
            'difference': reconciliation.difference,
        }

    @staticmethod
    @transaction.atomic
    def complete_reconciliation(
        reconciliation: BankReconciliation,
        completed_by,
    ) -> BankReconciliation:
        """Complete the bank reconciliation."""

        if not reconciliation.is_balanced:
            raise ValueError("Reconciliation must be balanced before completion.")

        reconciliation.status = BankReconciliation.Status.COMPLETED
        reconciliation.reconciled_by = completed_by
        reconciliation.completed_at = timezone.now()
        reconciliation.save()

        # Update bank account
        bank_account = reconciliation.bank_account
        bank_account.last_reconciled_date = reconciliation.statement_date
        bank_account.last_reconciled_balance = reconciliation.statement_balance
        bank_account.save()

        return reconciliation


class TransferService:
    """Service for bank transfers."""

    @staticmethod
    @transaction.atomic
    def create_transfer(
        organisation,
        transfer_date,
        amount: Decimal,
        from_account: BankAccount,
        to_account: BankAccount,
        created_by,
        memo: str = '',
        reference: str = '',
    ) -> Transfer:
        """Create a bank transfer."""

        transfer = Transfer.objects.create(
            organisation=organisation,
            transfer_date=transfer_date,
            amount=amount,
            from_account=from_account,
            to_account=to_account,
            memo=memo,
            reference=reference,
            created_by=created_by,
        )

        return transfer

    @staticmethod
    @transaction.atomic
    def process_transfer(transfer: Transfer, processed_by) -> Transfer:
        """Process a bank transfer and create journal entry."""

        if transfer.status != Transfer.Status.DRAFT:
            raise ValueError("Only draft transfers can be processed.")

        # Create journal entry
        lines = [
            {
                'account': transfer.to_account.account.id,
                'debit': transfer.amount,
                'credit': 0,
                'description': f"Transfer from {transfer.from_account.name}",
            },
            {
                'account': transfer.from_account.account.id,
                'debit': 0,
                'credit': transfer.amount,
                'description': f"Transfer to {transfer.to_account.name}",
            },
        ]

        journal_entry = JournalEntryService.create_entry(
            organisation=transfer.organisation,
            date=transfer.transfer_date,
            description=f"Bank Transfer: {transfer.from_account.name} to {transfer.to_account.name}",
            lines=lines,
            created_by=processed_by,
            source_type='bank_transfer',
            source_id=transfer.id,
        )

        JournalEntryService.post_entry(journal_entry, processed_by)

        transfer.status = Transfer.Status.COMPLETED
        transfer.journal_entry = journal_entry
        transfer.processed_by = processed_by
        transfer.processed_at = timezone.now()
        transfer.save()

        # Update bank account balances
        transfer.from_account.update_balance()
        transfer.to_account.update_balance()

        return transfer
