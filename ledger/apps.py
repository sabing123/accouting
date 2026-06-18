from django.apps import AppConfig


class LedgerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ledger"
    verbose_name = "General Ledger"

    def ready(self):
        from ledger.services import ChartOfAccountsService
        _ = ChartOfAccountsService  # Ensure services are loaded
