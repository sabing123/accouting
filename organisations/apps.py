from django.apps import AppConfig


class OrganisationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "organisations"
    verbose_name = "Organisations&Tenants"

    def ready(self):
        from organisations import signals
        from organisations import services
        super().ready()
        _ = services  # Ensure services are loaded
