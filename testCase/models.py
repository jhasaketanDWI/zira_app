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
        ordering = ("project", "parent__id", "name")
        permissions = [
            ("can_create_module", "User can create new test modules"),
            ("can_edit_module", "User can edit module details"),
            ("can_delete_module", "User can delete modules"),
            ("can_view_all_module","User can view all modules in a project"),
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
        permissions = [
            ("can_create_testTemplate", "User can create new template for testcase"),
            ("can_edit_testTemplate", "User can edit template details"),
            ("can_delete_testTemplate", "User can delete template"),
            ("can_view_all_testTemplate","User can view all template in a project"),
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
        permissions = [
            ("can_create_template_steps", "User can create new step for a template"),
            ("can_edit_template_steps", "User can edit steps of a template"),
            ("can_delete_template_steps", "User can delete steps"),
            ("can_view_all_template_steps","User can view all steps of a template of a project"),
        ]

    def __str__(self):
        return f"{self.template.name} - Template Step {self.order}"
    
    
class TestSuite(AuditBaseModel):
    SUITE_TYPE_CHOICES = [
        ("automation", "Automation"),
        ("manual", "Manual"),
    ]
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        ACTIVE = "ACTIVE", "Active"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        COMPLETED = "COMPLETED", "Completed"
        ARCHIVED = "ARCHIVED", "Archived"
        NOT_EXECUTED="NOT_EXECUTED", "Not_executed"

    project = models.ForeignKey(Project,related_name="suites",on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    suite_type = models.CharField(max_length=20, choices=SUITE_TYPE_CHOICES, default="manual")
    cases = models.ManyToManyField("QaTestCase",related_name="suites")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_EXECUTED)
    last_executed_on = models.DateTimeField(null=True,blank=True)
    
    class Meta:
            permissions = [
            ("can_create_suite", "User can create test suites"),
            ("can_edit_suite", "User can edit test suites"),
            ("can_delete_suite", "User can delete test suites"),
            ("can_view_all_suites","User can view all suits of a project"),
            ("can_add_testcases","User can add testcasses to suit")
        ]

    def __str__(self):
        return f"{self.project} :: {self.name}"
    

class QaTestCase(AuditBaseModel):
    class Meta:
         permissions = [
            ("can_create_testcase", "User can create new test case definitions"),
            ("can_edit_testcases", "User can edit test case details"),
            ("can_run_testcases", "User can run a test and report the pass/fail status"),
            ("can_manage_test_steps", "User can create and update Test Steps"),
            ("can_delete_testcase", "User can delete test cases"),
            ("can_view_all_testcases","User can view all testcase of a module"),
            ("can_edit_parent_module","can change module of a testcase"),
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
        NEGATIVE = 'NEGATIVE', 'Negative'
        SECURITY = 'SECURITY', 'Security'
        VALIDATION = 'VALIDATION', 'Validation'
        EDGE = 'EDGE', 'Edge Case'
        PERFORMANCE = 'PERFORMANCE', 'Performance'
        INTEGRATION = 'INTEGRATION', 'Integration'
        USABILITY = 'USABILITY', 'Usability'

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
        null=True,blank=True
    )
    project = models.ForeignKey(Project, related_name="testcases", on_delete=models.CASCADE, null=True, blank=True)

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
        permissions = [
            ("can_manage_step", "User can create, edit and delete testcase steps "),
            ("can_create_steps", "User can create test steps"),
            ("can_edit_steps", "User can edit test steps"),
            ("can_delete_steps", "User can delete test steps"),
            ("can_view_all_steps","User can view all steps of a testcase"),
        ]

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




