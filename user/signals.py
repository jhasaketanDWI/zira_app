from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import Group
from .models import User

@receiver(post_save, sender=User)
def sync_user_role_to_group(sender, instance, created, **kwargs):
    if instance.role:
        # This takes the string from your User model (e.g. "MANAGER")
        # And finds/creates the matching Django Group that holds the permissions
        group, _ = Group.objects.get_or_create(name=instance.role)
        instance.groups.add(group)