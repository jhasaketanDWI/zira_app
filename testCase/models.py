from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from common.models import AuditBaseModel
from project.models import Project  
from user.models import User

class TestCase(AuditBaseModel):
    class Source(models.TextChoices):
        MANUAL = 'MANUAL', 'Manual'
        AI_GENERATED = 'AI_GENERATED', 'AI Generated'
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        CRITICAL = 'CRITICAL', 'Critical'
    class TestType(models.TextChoices):
        FUNCTIONAL = 'FUNCTIONAL', 'Functional'
        SMOKE = 'SMOKE', 'Smoke'
        REGRESSION = 'REGRESSION', 'Regression'
        PERFORMANCE = 'PERFORMANCE', 'Performance'
        SECURITY = 'SECURITY', 'Security'
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        EXECUTED = 'EXECUTED', 'Executed'
        BLOCKED = 'BLOCKED', 'Blocked'

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    steps = models.TextField(help_text="Step-by-step instructions to execute the test.")
    expected_result = models.TextField(help_text="The expected outcome after executing the steps.")
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    test_type = models.CharField(max_length=20, choices=TestType.choices, default=TestType.FUNCTIONAL)


    project = models.ForeignKey(Project, on_delete=models.CASCADE,related_name='test_cases')
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.MANUAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
   
    assignee = models.ForeignKey(
       User ,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="test_cases"
    )
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


