from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

class AuditBaseModel(models.Model):
    """
    An abstract base class model that provides self-updating
    `created_at` and `updated_at` fields, and tracks the user
    who created or updated the record.
    """
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    # created_by = models.GenericIPAddressField(null=True, blank=True)  # Optional
    # updated_by = models.GenericIPAddressField(null=True, blank=True)  # Optional

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='%(class)s_created',
                                   on_delete=models.SET_NULL, null=True, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='%(class)s_updated',
                                   on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        # Ensure updated_at is always current
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)


class Comment(AuditBaseModel):
    body = models.TextField()
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')


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

