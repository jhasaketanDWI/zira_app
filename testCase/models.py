from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from common.models import AuditBaseModel
from project.models import Project  
from user.models import User



class Module(AuditBaseModel):
    project = models.ForeignKey(Project, related_name="qa_modules", on_delete=models.CASCADE)
    parent = models.ForeignKey(
        "self",
        related_name="children",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Parent module (null for top-level/root modules)"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    
    class Meta:
        unique_together = ("project", "parent", "name")
        ordering = ("project", "parent__id", "name")
        permissions = [
            ("can_create_module", "User can create new test modules"),
            ("can_edit_module", "User can edit module details"),
            ("can_delete_module", "User can delete modules"),
        ]

    def __str__(self):
        return f"{self.project.slug} / {self.name}"


class TestTemplate(AuditBaseModel):
    """
    Reusable template for manual test cases.
    Defines default steps that can be copied into real TestSteps.
    """
    project = models.ForeignKey(
        Project,
        related_name="test_templates",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("project", "name")
        permissions = [
            ("can_manage_test_templates", "User can create, edit, and delete test templates"),
        ]

    def __str__(self):
        return f"{self.project.slug} :: {self.name}"


class TemplateStep(models.Model):
    """
    Default step row that belongs to a template.
    Has the same shape as TestStep so we can clone easily.
    """
    template = models.ForeignKey(
        TestTemplate,
        related_name="template_steps",
        on_delete=models.CASCADE,
    )
    order = models.PositiveIntegerField(default=1)
    action = models.TextField()
    data = models.TextField(blank=True)
    expected = models.TextField(blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.template.name} - Template Step {self.order}"
    
    
class TestSuite(AuditBaseModel):
    SUITE_TYPE_CHOICES = [
        ("automation", "Automation"),
        ("manual", "Manual"),
    ]
    module = models.ForeignKey(Module, related_name="suites", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    suite_type = models.CharField(max_length=20, choices=SUITE_TYPE_CHOICES, default="manual")

    class Meta:
        unique_together = ("module", "name")
        permissions = [
            ("can_create_suite", "User can create test suites"),
            ("can_edit_suite", "User can edit test suites"),
            ("can_delete_suite", "User can delete test suites"),
        ]

    def __str__(self):
        return f"{self.module} :: {self.name}"
    

class QaTestCase(AuditBaseModel):
    class Meta:
         permissions = [
            ("can_create_testcase", "User can create new test case definitions"),
            ("can_edit_testcase", "User can edit test case details"),
            ("can_run_testcases", "User can run a test and report the pass/fail status"),
            ("can_link_test_to_task", "User can link a test case to a requirement (Task)"),
            ("can_manage_test_steps", "User can create and update Test Steps"),
            ("can_delete_testcase", "User can delete test cases"),
        ]
    class Priority(models.TextChoices):
        LOWEST = 'LOWEST', 'Lowest'
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        HIGHEST = 'HIGHEST', 'Highest'
    
    class Labels(models.TextChoices):
        FUNCTIONAL = 'FUNCTIONAL', 'Functional'
        SMOKE = 'SMOKE', 'Smoke'
        REGRESSION = 'REGRESSION', 'Regression'
        PERFORMANCE = 'PERFORMANCE', 'Performance'
        INTEGRATION = 'INTEGRATION', 'Integration'

    class Status(models.TextChoices):
        PASSED = 'PASSED', 'Passed'
        FAILED = 'FAILED', 'Failed'
        WARNING = 'WARNING', 'Warning'
        SKIPPED = 'SKIPPED', 'Skipped'
        NOT_EXECUTED = 'NOT_EXECUTED', 'Not_executed'      

    class Severity(models.TextChoices):
        BLOCKER = 'BLOCKER', 'Blocker'
        CRITICAL = 'CRITICAL', 'Critical'
        MAJOR = 'MAJOR', 'Major'
        MINOR = 'MINOR', 'Minor' 

    template = models.ForeignKey(TestTemplate,null=True,blank=True,on_delete=models.SET_NULL,related_name="cases",)
    suite = models.ForeignKey(TestSuite, related_name="cases", on_delete=models.CASCADE)
    labels = models.CharField(max_length=20, choices=Labels.choices, default=Labels.FUNCTIONAL)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.MINOR)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_EXECUTED)
    title = models.CharField(max_length=300)
    preconditions = models.TextField(blank=True)
    expected_result = models.TextField(blank=True)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM, db_index=True)
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name='testcases',
        null=True, blank=True
    )

    # optional: an NLP/scriptless description field
    natural_language = models.TextField(blank=True)

    def __str__(self):
        return self.title


class TestStep(models.Model):
    case = models.ForeignKey(QaTestCase, related_name="steps", on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=1)
    action = models.TextField()            # e.g., "Click Login button" or selector + action
    data = models.TextField(blank=True)    # optional data for step (input text, etc)
    expected = models.TextField(blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"{self.case.title} - Step {self.order}"


class Environment(models.Model):
    project = models.ForeignKey(Project, related_name="environments", on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    url = models.URLField(blank=True)
    details = models.JSONField(blank=True, null=True)
    class Meta:
        permissions = [
            ("can_manage_environments", "User can create and edit test environments"),
        ]

    def __str__(self):
        return f"{self.project.slug} / {self.name}"

class TestPlan(AuditBaseModel):
    project = models.ForeignKey(Project, related_name="testplans", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    suites = models.ManyToManyField(TestSuite, related_name="in_plans", blank=True)
    class Meta:
        permissions = [
            ("can_create_test_plan", "User can create new test plans"),
            ("can_edit_test_plan", "User can edit test plans"),
            ("can_delete_test_plan", "User can delete test plans"),
        ]
    def __str__(self):
        return f"{self.project.slug} :: {self.name}"


class TestRun(AuditBaseModel):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("RUNNING", "Running"),
        ("PASSED", "Passed"),
        ("FAILED", "Failed"),
        ("STOPPED", "Stopped"),
        ("ERROR", "Error"),
    ]
    project = models.ForeignKey(Project, related_name="testruns", on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    plan = models.ForeignKey(TestPlan, related_name="runs", on_delete=models.SET_NULL, null=True, blank=True)
    suites = models.ManyToManyField(TestSuite, related_name="runs", blank=True)
    environment = models.ForeignKey(Environment, null=True, blank=True, on_delete=models.SET_NULL)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="PENDING")
    meta = models.JSONField(default=dict, blank=True)
    class Meta:
        permissions = [
            ("can_create_test_run", "User can create new test runs"),
            ("can_execute_test_run", "User can execute/start test runs"),
            ("can_delete_test_run", "User can delete test runs"),
        ]

    def __str__(self):
        return f"{self.project.slug} :: {self.name}"


class TestExecution(models.Model):
    """Stores per-test-case execution result for a TestRun."""
    run = models.ForeignKey(TestRun, related_name="executions", on_delete=models.CASCADE)
    case = models.ForeignKey(QaTestCase, related_name="executions", on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=TestRun.STATUS_CHOICES, default="PENDING")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    log = models.TextField(blank=True)
    artifacts = models.JSONField(null=True, blank=True)  # e.g., screenshots, attachments
    executed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ("run", "case")
        permissions = [
            ("can_update_execution_status", "User can update the status of a specific test execution"),
        ]

    def duration(self):
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None







# class AutomationScript(AuditBaseModel):
#     class Framework(models.TextChoices):
#         SELENIUM = 'SELENIUM', 'Selenium'
#         PLAYWRIGHT = 'PLAYWRIGHT', 'Playwright'
#         CYPRESS = 'CYPRESS', 'Cypress'

#     class Status(models.TextChoices):
#         PENDING = 'PENDING', 'Pending'
#         IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
#         FAILED = 'FAILED', 'Failed'
#         READY = 'READY', 'Ready'

#     test_case = models.ForeignKey(TestCase, on_delete=models.CASCADE, related_name='scripts')
#     language = models.CharField(max_length=50)
#     framework = models.CharField(max_length=20, choices=Framework.choices)
#     script_content = models.TextField()
#     status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)


