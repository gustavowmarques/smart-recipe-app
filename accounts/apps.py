from django.apps import AppConfig


class AccountsConfig(AppConfig):
    """Django app configuration for the Accounts app.

    Registers application metadata and enables future signals or app-specific setup.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"
