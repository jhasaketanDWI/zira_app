from django.db import models
from common.models import AuditBaseModel
from project.models import Project, ProjectMember
from django.contrib.contenttypes.fields import GenericRelation
from django.conf import settings

class Status(AuditBaseModel):
    """
    Represents a status column in the Kanban board (e.g., To Do, In Progress).
    """
    # project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='statuses')
    title = models.CharField(max_length=100, unique=True)
    order = models.PositiveIntegerField(default=0,help_text="Order of the column on the board")

    class Meta:
        verbose_name_plural = "Statuses"
        ordering = ['order']

    def __str__(self):
        return self.title

class Epic(AuditBaseModel):
    status = models.ForeignKey(Status, on_delete=models.SET_NULL, null=True, blank=True, related_name='epics')
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.title

class Sprint(AuditBaseModel):
    name = models.CharField(max_length=255)
    goal = models.TextField(blank=True, null=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    duration = models.PositiveSmallIntegerField(
        default=2, 
        null=True, 
        blank=True, 
        help_text="Duration in weeks"
    )
    #  This field links a Sprint to one Epic.
    # This creates the "Epic contains Sprints" relationship.
    epic = models.ForeignKey(
        Epic,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sprints'  # Allows you to do epic.sprints.all()
    )
    is_active = models.BooleanField(default=False)
    is_ended = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.project.name} - {self.name}"



class Task(AuditBaseModel):

    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        LOWEST = 'LOWEST', 'Lowest'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        HIGHEST = 'HIGHEST', 'Highest'

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
    
    completed_at = models.DateTimeField(null=True, blank=True)

    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    parent_task = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subtasks')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    sprint = models.ForeignKey(
        Sprint, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='sprint_tasks' # Allows you to do sprint.tasks.all()
    )
    epic = models.ForeignKey(
        Epic, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='epic_tasks' # Allows you to do epic.tasks.all()
    )
    assignees = models.ManyToManyField(ProjectMember, related_name='assigned_tasks', blank=True)

    reporter = models.ForeignKey(ProjectMember, related_name='reported_tasks', on_delete=models.SET_NULL, null=True, blank=True)
    connected_items = models.ManyToManyField('self', blank=True, symmetrical=False)
    story_points = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Estimate of effort for the task")
    comments = GenericRelation('common.Comment', related_query_name='task')

    tags = models.ManyToManyField('Tag', through='TaskTag', related_name='tasks', blank=True)


    def __str__(self):
        return f"[{self.project.name}] {self.title}"



class Activity(AuditBaseModel):
    """
    A multi-purpose model to log activities like comments, status changes, etc.
    """
    task = models.ForeignKey(Task, related_name='activity_log', on_delete=models.CASCADE)
    comment = models.ForeignKey(
        'common.Comment',
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, 
        null=True,
        related_name='activities'
    )
    details = models.TextField(help_text="Stores the comment body or details of a change.")
    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.actor} on {self.task}"
    
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



class ActivityLog(AuditBaseModel):
    ACTION_TYPES = [
        ('CREATE', 'Created'),
        ('UPDATE', 'Updated'),
        ('COMMENT', 'Commented'),
        # ('STATUS_UPDATE', 'Status Updated'),
        # ('PRIORITY_UPDATE', 'Priority Updated'),
    ]
    
    project = models.ForeignKey('project.Project', on_delete=models.CASCADE, related_name='activities')
    task = models.ForeignKey('task.Task', on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action_type = models.CharField(max_length=20, choices=ACTION_TYPES) # This field now accepts the new types
    details = models.JSONField(default=dict)

    class Meta:
        ordering = ['-created_at']