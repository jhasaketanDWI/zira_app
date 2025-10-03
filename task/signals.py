from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Sprint, Task

# The @receiver decorator connects this function to the Sprint model's post_save signal.
@receiver(post_save, sender=Sprint)
def update_tasks_on_sprint_epic_change(sender, instance, created, **kwargs):
    """
    Listens for a Sprint to be saved. If its epic has been updated,
    this signal cascades the change down to all tasks within that sprint.
    """
    if created:
        return

    sprint = instance
    new_epic = sprint.epic
    tasks_to_update = sprint.tasks.exclude(epic=new_epic)
    if tasks_to_update.exists():
        tasks_to_update.update(epic=new_epic)