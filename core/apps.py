from django.apps import AppConfig


class CoreConfig(AppConfig):
    """App configuration for the core application (domain logic and views)."""
    
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
