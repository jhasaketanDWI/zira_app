from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from common.models import AuditBaseModel
from project.models import Project  

class TestCase(AuditBaseModel):
    class Source(models.TextChoices):
        MANUAL = 'MANUAL', 'Manual'
        AI_GENERATED = 'AI_GENERATED', 'AI Generated'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        EXECUTED = 'EXECUTED', 'Executed'
        BLOCKED = 'BLOCKED', 'Blocked'

    title = models.CharField(max_length=255)
    steps = models.TextField()
    expected_result = models.TextField()
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    def __str__(self):
        return self.title


class AutomationScript(AuditBaseModel):
    class Framework(models.TextChoices):
        SELENIUM = 'SELENIUM', 'Selenium'
        PLAYWRIGHT = 'PLAYWRIGHT', 'Playwright'
        CYPRESS = 'CYPRESS', 'Cypress'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        FAILED = 'FAILED', 'Failed'
        READY = 'READY', 'Ready'

    test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name='scripts')
    language = models.CharField(max_length=50)
    framework = models.CharField(max_length=20, choices=Framework.choices)
    script_content = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)


