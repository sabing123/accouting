from celery import shared_task
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def send_email_notification(self, subject, body, to_emails, from_email=None, html_body=None):
    """Send email notification."""
    from django.core.mail import send_mail

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            recipient_list=to_emails,
            html_message=html_body,
            fail_silently=False,
        )
        return {'status': 'sent', 'to': to_emails}
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        self.retry(exc=e, countdown=60)


@shared_task
def process_recurring_journal_entries():
    """Process recurring journal entries that are due today."""
    from ledger.models import RecurringJournalEntry

    today = timezone.now().date()
    recurring_entries = RecurringJournalEntry.objects.filter(
        is_active=True,
        next_run_date=today,
    )

    processed = []
    for entry in recurring_entries:
        try:
            if entry.should_run(today):
                journal_entry = entry.create_entry(today, entry.created_by)
                processed.append({
                    'recurring_id': str(entry.id),
                    'journal_entry_id': str(journal_entry.id),
                    'status': 'success',
                })
        except Exception as e:
            logger.error(f"Failed to process recurring entry {entry.id}: {e}")
            processed.append({
                'recurring_id': str(entry.id),
                'status': 'error',
                'error': str(e),
            })

    return processed


@shared_task
def process_recurring_invoices():
    """Process recurring invoices that are due today."""
    from receivables.models import RecurringInvoice
    from receivables.services import InvoiceService

    today = timezone.now().date()
    recurring_invoices = RecurringInvoice.objects.filter(
        is_active=True,
        next_run_date=today,
    )

    processed = []
    for template in recurring_invoices:
        try:
            if template.should_run(today):
                invoice = InvoiceService.create_invoice(
                    organisation=template.organisation,
                    customer=template.customer,
                    invoice_date=today,
                    lines=template.template_lines,
                    created_by=template.created_by,
                )

                # Send invoice
                InvoiceService.send_invoice(invoice, template.created_by)

                processed.append({
                    'template_id': str(template.id),
                    'invoice_id': str(invoice.id),
                    'status': 'success',
                })
        except Exception as e:
            logger.error(f"Failed to process recurring invoice {template.id}: {e}")
            processed.append({
                'template_id': str(template.id),
                'status': 'error',
                'error': str(e),
            })

    return processed


@shared_task
def update_account_balances(organisation_id=None):
    """Update account balances for all or specific organisation."""
    from ledger.models import Account
    from organisations.models import Organisation

    if organisation_id:
        accounts = Account.objects.filter(organisation_id=organisation_id)
    else:
        accounts = Account.objects.all()

    updated = []
    for account in accounts:
        try:
            account.update_balance()
            updated.append({
                'account_id': str(account.id),
                'new_balance': str(account.current_balance),
            })
        except Exception as e:
            logger.error(f"Failed to update account {account.id}: {e}")

    return updated


@shared_task
def send_overdue_notifications():
    """Send notification emails for overdue invoices."""
    from receivables.models import Invoice

    today = timezone.now().date()
    overdue_invoices = Invoice.objects.filter(
        status__in=['sent', 'partial'],
        due_date__lt=today,
    ).select_related('customer', 'organisation')

    notifications_sent = []
    for invoice in overdue_invoices:
        try:
            send_email_notification.delay(
                subject=f"Overdue Invoice: {invoice.invoice_number}",
                body=f"Invoice {invoice.invoice_number} for {invoice.customer.name} "
                     f"is {invoice.days_overdue} days overdue. Balance: ${invoice.balance}",
                to_emails=[invoice.organisation.email],
            )
            notifications_sent.append(str(invoice.id))
        except Exception as e:
            logger.error(f"Failed to send overdue notification for {invoice.id}: {e}")

    return notifications_sent


@shared_task
def send_upcoming_payment_reminders():
    """Send reminders for upcoming bill payments."""
    from payables.models import Bill

    today = timezone.now().date()
    upcoming_bills = Bill.objects.filter(
        status__in=['open', 'partial'],
        due_date__lte=today + timedelta(days=7),
        due_date__gte=today,
    ).select_related('vendor', 'organisation')

    reminders_sent = []
    for bill in upcoming_bills:
        try:
            days_until_due = (bill.due_date - today).days
            send_email_notification.delay(
                subject=f"Upcoming Payment: {bill.bill_number}",
                body=f"Bill {bill.bill_number} from {bill.vendor.name} "
                     f"is due in {days_until_due} days. Amount: ${bill.balance}",
                to_emails=[bill.organisation.email],
            )
            reminders_sent.append(str(bill.id))
        except Exception as e:
            logger.error(f"Failed to send payment reminder for {bill.id}: {e}")

    return reminders_sent


@shared_task
def cleanup_expired_trials():
    """Marks expired trials as expired and sends notifications."""
    from organisations.models import Organisation

    today = timezone.now().date()
    expired_trials = Organisation.objects.filter(
        subscription_status='trial',
        trial_ends_at__lt=today,
    )

    expired = []
    for org in expired_trials:
        try:
            org.subscription_status = 'expired'
            org.save()

            send_email_notification.delay(
                subject="Trial Expired",
                body=f"Your trial for {org.name} has expired. "
                     "Please upgrade to continue using the service.",
                to_emails=[org.email],
            )

            expired.append(str(org.id))
        except Exception as e:
            logger.error(f"Failed to expire trial for {org.id}: {e}")

    return expired


@shared_task
def generate_scheduled_reports(organisation_id, report_type, **params):
    """Generate and send scheduled reports."""
    from reports.services import (
        TrialBalanceService, BalanceSheetService, IncomeStatementService
    )
    from organisations.models import Organisation

    org = Organisation.objects.get(id=organisation_id)

    report_data = {}
    if report_type == 'trial_balance':
        report_data = TrialBalanceService.generate(org, params.get('as_of'))
    elif report_type == 'balance_sheet':
        report_data = BalanceSheetService.generate(org, params.get('as_of'))
    elif report_type == 'income_statement':
        report_data = IncomeStatementService.generate(
            org,
            params.get('start_date'),
            params.get('end_date')
        )

    # Send as email attachment
    if params.get('send_email'):
        send_email_notification.delay(
            subject=f"{report_type.title()} Report - {org.name}",
            body=f"Please find attached the {report_type} report.",
            to_emails=params.get('recipients', [org.email]),
        )

    return {
        'organisation': str(org.id),
        'report_type': report_type,
        'status': 'generated',
    }


@shared_task
def sync_stripe_subscriptions():
    """Sync subscription status with Stripe."""
    import stripe
    stripe.api_key = settings.STRIPE_API_KEY

    from billing.models import Subscription

    subscriptions = Subscription.objects.filter(
        stripe_subscription_id__isnull=False,
        status__in=['active', 'trialing', 'past_due']
    )

    synced = []
    for subscription in subscriptions:
        try:
            stripe_sub = stripe.Subscription.retrieve(subscription.stripe_subscription_id)

            # Update status
            status_map = {
                'active': 'active',
                'trialing': 'trialing',
                'past_due': 'past_due',
                'canceled': 'cancelled',
            }

            subscription.status = status_map.get(stripe_sub.status, subscription.status)
            subscription.current_period_start = timezone.datetime.fromtimestamp(
                stripe_sub.current_period_start, tz=timezone.utc
            )
            subscription.current_period_end = timezone.datetime.fromtimestamp(
                stripe_sub.current_period_end, tz=timezone.utc
            )
            subscription.save()

            synced.append(str(subscription.id))
        except Exception as e:
            logger.error(f"Failed to sync subscription {subscription.id}: {e}")

    return synced


@shared_task
def recalculate_period_totals():
    """Recalculate period totals for all accounts."""
    from ledger.models import Account, FiscalPeriod, JournalEntryLine
    from django.db.models import Sum

    # Get current period
    today = timezone.now().date()
    current_period = FiscalPeriod.objects.filter(
        start_date__lte=today,
        end_date__gte=today
    ).first()

    if not current_period:
        return {'status': 'no_current_period'}

    accounts = Account.objects.filter(organisation=current_period.organisation)

    updated = []
    for account in accounts:
        try:
            # Calculate period totals
            totals = JournalEntryLine.objects.filter(
                account=account,
                entry__fiscal_period=current_period,
                entry__status='posted'
            ).aggregate(
                total_debit=Sum('debit_amount'),
                total_credit=Sum('credit_amount')
            )

            account.period_debit = totals['total_debit'] or 0
            account.period_credit = totals['total_credit'] or 0
            account.save()

            updated.append(str(account.id))
        except Exception as e:
            logger.error(f"Failed to update period totals for {account.id}: {e}")

    return updated
