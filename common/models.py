from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from common.middleware import get_current_user
from .manager import SoftDeleteManager


class SoftDeleteModel(models.Model):
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    
    objects = SoftDeleteManager() 
    
    all_objects = models.Manager() 

    def soft_delete(self):
        """Marks the instance as deleted."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()

    def restore(self):
        """Restores a soft-deleted instance."""
        self.is_deleted = False
        self.deleted_at = None
        self.save()

    # Override the default delete() method to prevent hard deletion
    def delete(self, *args, **kwargs):
        """
        Instead of a hard delete, we perform a soft delete.
        """
        self.soft_delete()

    class Meta:
        abstract = True
class AuditBaseModel(SoftDeleteModel):
    """
    An abstract base class model that provides self-updating
    `created_at` and `updated_at` fields, and tracks the user
    who created or updated the record.
    """
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='%(class)s_created',
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='%(class)s_updated',
        on_delete=models.SET_NULL,
        null=True, blank=True
    )
   

    class Meta:
        abstract = True
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        user = get_current_user()
        if not self.pk and not self.created_by:
            self.created_by = user
        self.updated_by = user
        super().save(*args, **kwargs)


class Comment(AuditBaseModel):
    """
    Represents a comment made by a user on a specific task.
    """
    # task = models.ForeignKey(
    #     'task.Task', 
    #     related_name='comments', 
    #     on_delete=models.CASCADE,
    #     help_text="The task this comment belongs to.",
    #     null=True  
    # )
    author = models.ForeignKey(
        'project.ProjectMember', # Was settings.AUTH_USER_MODEL
        on_delete=models.SET_NULL,
        null=True,
        related_name='task_comments',
        help_text="The project member who wrote the comment."
    )
    body = models.TextField(
        help_text="The content of the comment."
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    object_id = models.PositiveIntegerField(null=True)
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        ordering = ['-created_at'] 

    def __str__(self):
            return f"Comment by {self.author} : {self.body[:40]}..."

        # return f"Comment by {self.author} on {self.task}"


class Notification(AuditBaseModel):
    class NotificationType(models.TextChoices):
        GENERAL = 'GENERAL', 'General'
        COMMENT = 'COMMENT', 'Comment'
        TASK_ASSIGNMENT = 'TASK_ASSIGNMENT', 'Task Assignment'
        SPRINT_UPDATE = 'SPRINT_UPDATE', 'Sprint Update'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = models.CharField(max_length=255)
    notification_type = models.CharField(max_length=20, choices=NotificationType.choices)
    is_read = models.BooleanField(default=False)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')



class Attachment(AuditBaseModel):
    file = models.FileField(upload_to='attachments/')
    description = models.CharField(max_length=255, blank=True, null=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

