from .base import *  # noqa: F401, F403

DEBUG = True

# Allow all hosts in development
ALLOWED_HOSTS = ["*"]

# Debug toolbar
INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.common.CommonMiddleware") + 1,
    "debug_toolbar.middleware.DebugToolbarMiddleware",
)
INTERNAL_IPS = ["127.0.0.1", "::1"]

# Email backend for development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Use development settings for allauth
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = False

# Django Axes relaxed
AXES_FAILURE_LIMIT = 20
AXES_COOLOFF_TIME = timedelta(minutes=5)

# Debug toolbar settings
DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
}

# CORS for development
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# Use simpler static files storage
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Cache timeout reduced for development
CACHES["default"]["TIMEOUT"] = 300

# Disable throttling
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {}

# Use Werkzeug debugger
if DEBUG and "runserver" in sys.argv:
    import django_extensions.management.commands.runserver_plus


# Enable logging for SQLAlchemy queries
LOGGING["loggers"]["django.db.backends"] = {
    "handlers": ["console"],
    "level": "DEBUG",
    "propagate": False,
}
