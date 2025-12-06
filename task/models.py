from django.db import models
from common.models import AuditBaseModel
from project.models import Project, ProjectMember
from django.contrib.contenttypes.fields import GenericRelation
from django.conf import settings
from django.utils import timezone


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

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='owned_sprints'
    )
    is_active = models.BooleanField(default=False)
    is_ended = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.project.name} - {self.name}"


class Goal(AuditBaseModel):
    class StatusLabel(models.TextChoices):
        ON_TRACK = 'ON_TRACK', 'On Track'
        AT_RISK = 'AT_RISK', 'At Risk'
        OFF_TRACK = 'OFF_TRACK', 'Off Track'

    # Required for permission/multitenancy logic, even if "only" fields requested
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='goals')

    # 1. SPRINT LINKING: One Sprint = One Goal
    sprint = models.OneToOneField(
        'task.Sprint', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='sprint_goal'
    )

    # 2. PARENT GOALS: For hierarchy
    parent = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='sub_goals'
    )

    # 3. DESCRIPTION & TITLE
    # The UI images show a short name/title is needed for the list view
    title = models.CharField(max_length=255, help_text="Short name of the goal")
    description = models.TextField(blank=True, null=True, help_text="Detailed description")
    
    owner = models.ForeignKey(
        ProjectMember, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='owned_goals'
    )

    # 5. MANUAL OVERRIDES
    _manual_progress = models.PositiveSmallIntegerField(default=0)
    _manual_status = models.CharField(
        max_length=20, 
        choices=StatusLabel.choices, 
        default=StatusLabel.ON_TRACK
    )

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        """
        AUTOMATION: 
        1. Check if this goal is linked to a Sprint.
        2. Check if that Sprint has an 'owner' (User).
        3. Find the 'ProjectMember' profile for that User in this Project.
        4. Assign that ProjectMember as the Goal owner.
        """
        if self.sprint and self.sprint.owner:
            # Find the ProjectMember for the sprint owner
            sprint_owner_member = ProjectMember.objects.filter(
                user=self.sprint.owner,
                project=self.project
            ).first()
            
            # Set the goal owner to match the sprint owner
            if sprint_owner_member:
                self.owner = sprint_owner_member
                
        super().save(*args, **kwargs)

    # 6. DYNAMIC STATUS & PROGRESS (The "Status" Field)
    @property
    def progress_percentage(self):
        # If linked to a sprint, calculate based on time elapsed
        if self.sprint and self.sprint.start_date and self.sprint.end_date:
            total_duration = (self.sprint.end_date - self.sprint.start_date).days
            if total_duration <= 0: return 0
            
            elapsed = (timezone.now().date() - self.sprint.start_date).days
            
            if elapsed < 0: return 0 
            if elapsed > total_duration: return 100 
            
            return int((elapsed / total_duration) * 100)
            
        # Fallback to manual input for non-sprint goals
        return self._manual_progress 

    @property
    def status_label(self):
        # If linked to a sprint, calculate based on end date proximity
        if self.sprint and self.sprint.end_date:
            today = timezone.now().date()
            days_remaining = (self.sprint.end_date - today).days

            if days_remaining < 0:
                return self.StatusLabel.OFF_TRACK
            elif days_remaining <= 3: 
                return self.StatusLabel.AT_RISK
            else:
                return self.StatusLabel.ON_TRACK

        # Fallback to manual input for non-sprint goals
        return self._manual_status
    

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

    #stores the specific form answers (e.g. {"browser": "Chrome", "steps": "..."})
    form_data = models.JSONField(default=dict, blank=True, help_text="Dynamic data from custom forms")


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

# NEW MODEL: Stores the design of the form from your React Editor
class FormTemplate(AuditBaseModel):
    class FormType(models.TextChoices):
        BUG = 'BUG', 'Bug'
        FEATURE = 'FEATURE', 'Feature'
        IMPROVEMENT = 'IMPROVEMENT', 'Improvement'
        

    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='forms')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    task_type = models.CharField(max_length=20, choices=FormType.choices, default=FormType.FEATURE)
    
    assignees = models.ManyToManyField(
        'project.ProjectMember', 
        related_name='form_templates_assigned',  
        blank=True
    )
    # Stores the "fields" array from your React frontend
    structure = models.JSONField(default=list, help_text="Form fields schema")
    
    # Matches frontend 'type': 'template' vs 'custom'
    is_system_template = models.BooleanField(default=False) 
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_forms')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='updated_forms')

    def __str__(self):
        return f"{self.title} ({self.project.name})"

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