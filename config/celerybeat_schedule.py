from celery.schedules import crontab
from celery import Celery

app = Celery('accounting_saas')

CELERYBEAT_SCHEDULE = {
    # Daily tasks
    'process-recurring-entries': {
        'task': 'config.celery_tasks.process_recurring_journal_entries',
        'schedule': crontab(hour=1, minute=0),  # Run at 1 AM
    },
    'process-recurring-invoices': {
        'task': 'config.celery_tasks.process_recurring_invoices',
        'schedule': crontab(hour=2, minute=0),  # Run at 2 AM
    },
    'send-overdue-notifications': {
        'task': 'config.celery_tasks.send_overdue_notifications',
        'schedule': crontab(hour=9, minute=0),  # Run at 9 AM
    },
    'cleanup-expired-trials': {
        'task': 'config.celery_tasks.cleanup_expired_trials',
        'schedule': crontab(hour=3, minute=0),  # Run at 3 AM
    },
    'sync-stripe-subscriptions': {
        'task': 'config.celery_tasks.sync_stripe_subscriptions',
        'schedule': crontab(hour=4, minute=0),  # Run at 4 AM
    },

    # Weekly tasks
    'send-payment-reminders': {
        'task': 'config.celery_tasks.send_upcoming_payment_reminders',
        'schedule': crontab(day_of_week=1, hour=9, minute=0),  # Monday at 9 AM
    },

    # Monthly tasks
    'recalculate-period-totals': {
        'task': 'config.celery_tasks.recalculate_period_totals',
        'schedule': crontab(day_of_month=1, hour=0, minute=0),  # First day of month
    },
}

app.conf.beat_schedule = CELERYBEAT_SCHEDULE
