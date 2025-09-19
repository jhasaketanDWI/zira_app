from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import AbstractUser, BaseUserManager
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
    created_by = models.GenericIPAddressField(null=True, blank=True)  # Optional
    updated_by = models.GenericIPAddressField(null=True, blank=True)  # Optional

    # created_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='%(class)s_created',
    #                                on_delete=models.SET_NULL, null=True, blank=True)
    # updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='%(class)s_updated',
    #                                on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        # Ensure updated_at is always current
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

class CustomUserManager(BaseUserManager):

    def create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('The Email must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'ADMIN')  # Default role for superuser

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser, AuditBaseModel):

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        OWNER = "OWNER", "Owner"
        MANAGER = "MANAGER", "Manager"
        DEVELOPER = "DEVELOPER", "Developer"
        TESTER = "TESTER", "Tester"

    # We don't need a username, email will be our unique identifier
    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=50, choices=Role.choices,default=Role.DEVELOPER)

    # Add related_name to resolve clashes with default User model
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
        related_name="custom_user_groups",
        related_query_name="user",
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name="custom_user_permissions",
        related_query_name="user",
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return f"{self.email} ({self.role})"


# ----------------------------
# Project Models
# ----------------------------
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


class Epic(AuditBaseModel):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Open'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        DONE = 'DONE', 'Done'
        ARCHIVED = 'ARCHIVED', 'Archived'

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    def __str__(self):
        return self.title


class Sprint(AuditBaseModel):
    name = models.CharField(max_length=255)
    goal = models.TextField(blank=True, null=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False)
    is_ended = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.project.name} - {self.name}"


class Task(AuditBaseModel):
    class Status(models.TextChoices):
        TODO = 'TODO', 'To Do'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        IN_REVIEW = 'IN_REVIEW', 'In Review'
        DONE = 'DONE', 'Done'

    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        CRITICAL = 'CRITICAL', 'Critical'

    class TaskType(models.TextChoices):
        BUG = 'BUG', 'Bug'
        FEATURE = 'FEATURE', 'Feature'
        IMPROVEMENT = 'IMPROVEMENT', 'Improvement'
        TEST_CASE = 'TEST_CASE', 'Test Case'

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO)
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    task_type = models.CharField(max_length=20, choices=TaskType.choices)

    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    sprint = models.ForeignKey(Sprint, on_delete=models.SET_NULL, null=True, blank=True)
    epic = models.ForeignKey(Epic, on_delete=models.SET_NULL, null=True, blank=True)

    assignee = models.ForeignKey(ProjectMember, related_name='assigned_tasks', on_delete=models.SET_NULL, null=True, blank=True)
    reporter = models.ForeignKey(ProjectMember, related_name='reported_tasks', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"[{self.project.name}] {self.title}"


class Tag(AuditBaseModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, blank=True, null=True)

    class Meta:
        unique_together = ('project', 'name')

    def __str__(self):
        return self.name


class TaskTag(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('task', 'tag')


# ----------------------------
# Test Case / Automation / Attachment
# ----------------------------
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


class Attachment(AuditBaseModel):
    file = models.FileField(upload_to='attachments/')
    description = models.CharField(max_length=255, blank=True, null=True)

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')


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


# ----------------------------
# Subscription / Invoice
# ----------------------------
class SubscriptionPlan(AuditBaseModel):
    name = models.CharField(max_length=100)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2)
    user_limit = models.IntegerField()
    testcase_limit = models.IntegerField()
    project_limit = models.IntegerField()
    features = models.JSONField(default=dict)

    def __str__(self):
        return self.name


class Subscription(AuditBaseModel):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.owner.email}'s {self.plan.name} Plan"


class Invoice(AuditBaseModel):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    period_start = models.DateField()
    period_end = models.DateField()
    paid = models.BooleanField(default=False)
    external_ref = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Invoice {self.id} for {self.subscription.owner.email}"

class Ticket(AuditBaseModel):
    class Status(models.TextChoices):
        TODO = "TODO", "To Do"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        DONE = "DONE", "Done"

    sprint = models.ForeignKey(Sprint, on_delete=models.CASCADE, related_name="tickets")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO)

    def __str__(self):
        return f"{self.title} ({self.status})"
