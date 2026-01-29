from django.apps import AppConfig
from django.db.models.signals import post_migrate

class UserConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'user'
    verbose_name = 'User Management'
    def ready(self):
        import user.signals
        post_migrate.connect(run_init_roles, sender=self)





def run_init_roles(sender, **kwargs):
    from django.core.management import call_command
    try:
        call_command('init_roles')
    except Exception:
        pass # Fail silently during initial DB creation