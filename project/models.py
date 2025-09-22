from django.db import models
from django.conf import settings
from django.utils import timezone
from common.models import AuditBaseModel

class Project(AuditBaseModel):
    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planned'
        ONGOING = 'ONGOING', 'Ongoing'
        DELAYED = 'DELAYED', 'Delayed'
        COMPLETED = 'COMPLETED', 'Completed'
        ARCHIVED = 'ARCHIVED', 'Archived'

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='owned_projects', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)

    def __str__(self):
        return self.name


class ProjectMember(AuditBaseModel):
    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        PROJECT_MANAGER = 'PROJECT_MANAGER', 'Project Manager'
        DEVELOPER = 'DEVELOPER', 'Developer'
        TESTER = 'TESTER', 'Tester'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        unique_together = ('user', 'project')

    def __str__(self):
        return f"{self.user.email} in {self.project.name} as {self.role}"
