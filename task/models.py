from django.db import models
from common.models import AuditBaseModel
from project.models import Project, ProjectMember

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

class Status(AuditBaseModel):
    """
    Represents a status column in the Kanban board (e.g., To Do, In Progress).
    """
    title = models.CharField(max_length=100, unique=True)
    # You can add an 'order' field here later to manage column order on a board
    # order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name_plural = "Statuses"

    def __str__(self):
        return self.title

class Task(AuditBaseModel):

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
    status = models.ForeignKey(Status, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    priority = models.CharField(max_length=20, choices=Priority.choices, default=Priority.MEDIUM)
    task_type = models.CharField(max_length=20, choices=TaskType.choices, default=TaskType.FEATURE)
    # due_date = models.DateTimeField(null=True, blank=True)

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    sprint = models.ForeignKey(Sprint, on_delete=models.SET_NULL, null=True, blank=True)
    epic = models.ForeignKey(Epic, on_delete=models.SET_NULL, null=True, blank=True)

    assignee = models.ForeignKey(ProjectMember, related_name='assigned_tasks', on_delete=models.SET_NULL, null=True,
                                 blank=True)
    reporter = models.ForeignKey(ProjectMember, related_name='reported_tasks', on_delete=models.SET_NULL, null=True,
                                 blank=True)

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


class Ticket(AuditBaseModel):
    class Status(models.TextChoices):
        TODO = "TODO", "To Do"
        IN_PROGRESS = "IN_PROGRESS", "In Progress"
        DONE = "DONE", "Done"

    sprint = models.ForeignKey(Sprint, on_delete=models.CASCADE, related_name="tickets")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assignee = models.ForeignKey(
        ProjectMember, on_delete=models.SET_NULL, null=True, blank=True, related_name="tickets"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.TODO)

    def __str__(self):
        return f"{self.title} ({self.status})"

