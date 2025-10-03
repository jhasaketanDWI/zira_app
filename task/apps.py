from django.apps import AppConfig


class TaskConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'task'
    def ready(self):
        # This line imports your signals file, connecting the receivers.
        import task.signals


    