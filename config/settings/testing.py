from .base import *  # noqa: F401, F403

DEBUG = False

# Use in-memory database for testing
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "test_accounting_saas",
        "USER": "postgres",
        "PASSWORD": "postgres",
        "HOST": "db",
        "PORT": "5432",
        "TEST": {
            "CHARSET": "utf8",
            "COLLATION": "utf8_general_ci",
        },
    }
}

# Speed up tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable migrations for faster tests
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()

# Email backend for testing
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Celery
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable audit logging in tests
AUDITLOG_INCLUDE_ALL_MODELS = False

# Faster password hashing
ACCOUNT_EMAIL_VERIFICATION = "optional"

# Use simple secret key for tests
SECRET_KEY = "test-secret-key-do-not-use-in-production"

CELERY_BROKER_URL = "memory://"

LOGGING = {}
