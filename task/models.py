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
        permissions = [
            ("can_create_status", "User can create new Kanban statuses/columns"),
            ("can_edit_status", "User can rename or update existing statuses"),
            ("can_delete_status", "User can delete a status column"),
            ("can_reorder_status", "User can change the order of status columns"),
        ]
   

    def __str__(self):
        return self.title

class Epic(AuditBaseModel):
    class Meta:
        permissions = [
            ("can_create_epic", "User can create new Epics"),
            ("can_edit_epic", "User can modify Epic details"),
            ("can_delete_epic", "User can delete Epics"),
        ]
    status = models.ForeignKey(Status, on_delete=models.SET_NULL, null=True, blank=True, related_name='epics')
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.title

class Sprint(AuditBaseModel):
    class Meta:
        permissions = [
            ("can_create_sprint", "User can create a new sprint"),
            ("can_start_sprint", "User can activate an upcoming sprint"),
            ("can_end_sprint", "User can close an active sprint"),
            ("can_move_to_backlog", "User can move items between a sprint and the backlog"),
            ("can_edit_sprint", "User can edit sprint details"),
        ]
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
    class Meta:
        permissions = [
            ("can_create_goal", "User can define new project goals"),
            ("can_edit_goal", "User can update goal progress/status"),
            ("can_delete_goal", "User can remove goals"),
            ("can_view_goals", "User can view project goals"),
        ]
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
    class Meta:
        permissions = [
            ("can_create_task", "User can create new Tasks/Tickets/Bugs"),
            ("can_edit_tasks", "User can edit the title, description, and fields of any task"),
            ("can_edit_task_own", "User can only edit tasks they reported/created"),
            ("can_assign_task", "User can assign a task to any other project member or himself"),
            ("can_change_status", "User can change the status of a task"),
            ("can_change_priority", "User can change task priority"),
            ("can_add_comment", "User can add comments to a task"),
            ("can_manage_attachments", "User can add/remove attachments from a task"),
            ("can_delete_task", "User can permanently delete tasks"),
            ("can_view_all_tasks", "User can view tasks in the project"),
            ("can_set_due_date", "User can set or modify task due dates"),
            ("can_edit_story_points", "User can set or change story point estimates"),
            ("can_link_tasks", "User can link tasks to other tasks")
            
        ]

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
        permissions = [
            ("can_create_tag", "User can create new tags"),
            ("can_delete_tag", "User can delete tags"),
             # Editing tags (renaming) affects all tasks, so it's a higher privilege
            ("can_manage_tags", "User can rename or merge tags"),
        ]

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

class FormTemplate(AuditBaseModel):
    class Meta:
        permissions = [
            ("can_create_form_template", "User can design new form templates"),
            ("can_edit_form_template", "User can modify form structures"),
            ("can_delete_form_template", "User can delete form templates"),
            # Note: Submitting a form usually just requires 'can_create_task', 
            # but if you want it specific:
            ("can_submit_form", "User can submit entries via forms"), 
        ]
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