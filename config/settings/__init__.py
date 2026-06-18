import os

settings_module = os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.base")

if settings_module == "config.settings.base":
    from .base import *
elif "production" in settings_module:
    from .production import *
elif "testing" in settings_module:
    from .testing import *
elif "development" in settings_module:
    from .development import *
else:
    from .base import *
