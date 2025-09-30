from django.db import models
from common.models import AuditBaseModel
from project.models import Project, ProjectMember
from django.contrib.contenttypes.fields import GenericRelation

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
    due_date = models.DateField(null=True, blank=True)
    # Self-referencing key for subtasks
    parent_task = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subtasks')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    # sprint = models.ForeignKey(Sprint, on_delete=models.SET_NULL, null=True, blank=True)
    # UPDATED: Added related_name for easier lookups from a sprint instance.
    sprint = models.ForeignKey(
        Sprint, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='tasks' # Allows you to do sprint.tasks.all()
    )
    # epic = models.ForeignKey(Epic, on_delete=models.SET_NULL, null=True, blank=True)
    # This field correctly links a Task to its parent Epic.
    epic = models.ForeignKey(
        Epic, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='tasks' # Allows you to do epic.tasks.all()
    )
    assignees = models.ManyToManyField(ProjectMember, related_name='assigned_tasks', blank=True)

    reporter = models.ForeignKey(ProjectMember, related_name='reported_tasks', on_delete=models.SET_NULL, null=True,
    
                                 blank=True)
    # ADDED: A way to link 'Connected work items' together. This does not create a new model.
    connected_items = models.ManyToManyField('self', blank=True, symmetrical=False)
    story_points = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Estimate of effort for the task")
    
    # This field will store a list of events, e.g., [{"user": "x", "timestamp": "y", "type": "status_change", "details": "Moved to In Progress"}]
    # activity_history = models.JSONField(default=list,null=True, blank=True, help_text="Stores a log of all activities like history and work logs on this task.")
    # activity_history = models.ManyToManyField(Activity, related_name='assigned_tasks', blank=True)

    # ADDED: Generic relation to the existing 'common.Comment' model for the comments feed.
    # This is not a new model, but a link to the generic Comment model you likely already have for your project.
    comments = GenericRelation('common.Comment', related_query_name='task')

    tags = models.ManyToManyField('Tag', through='TaskTag', related_name='tasks', blank=True)


    def __str__(self):
        return f"[{self.project.name}] {self.title}"

class Activity(AuditBaseModel):
    task = models.ForeignKey(Task, related_name='activity_log', on_delete=models.CASCADE)
    type = models.CharField(max_length=50)
    details = models.TextField()
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

