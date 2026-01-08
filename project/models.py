from django.db import models
from django.conf import settings
from django.utils import timezone
from common.models import AuditBaseModel
import uuid
from organizations.models import Organization

class Project(AuditBaseModel):
    class Meta:
        permissions = [
            ("can_create_project", "User can create a brand new project instance"),
            ("can_edit_project_details", "User can change project name, key, and description"),
            ("can_archive_project", "User can archive or restore the project"),
            ("can_manage_project_members", "User can add, remove, and change the roles of other users"),
            ("can_manage_workflows", "User can create and edit custom workflow schemes"),
            # ("can_have_full_project_access", "User can do any changes on project including task, sprint, epic etc"),
            ("can_delete_project", "User can delete a project"),
            ("can_view_project_summary","can_view_project_settings")
        ]
    class Status(models.TextChoices):
        PLANNED = 'PLANNED', 'Planned'
        ONGOING = 'ONGOING', 'Ongoing'
        DELAYED = 'DELAYED', 'Delayed'
        COMPLETED = 'COMPLETED', 'Completed'
        ARCHIVED = 'ARCHIVED', 'Archived'

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='projects',
        null=True,
        blank=True
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='owned_projects', on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)

    def __str__(self):
        return self.name


class ProjectMember(AuditBaseModel):
    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        MANAGER = 'MANAGER', 'Manager'
        SCRUM_MASTER = "SCRUM_MASTER", "Scrum Master" 
        DEVELOPER = 'DEVELOPER', 'Developer'
        TESTER = 'TESTER', 'Tester'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        unique_together = ('user', 'project')

    def __str__(self):
        return f"{self.user.email} in {self.project.name} as {self.role}"

class ProjectInvitation(AuditBaseModel):
    """
    Tracks invitations for users to join specific projects.
    Handles both new and existing users.
    """
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='invitations')
    email = models.EmailField(help_text="Email of the person being invited.")
    role = models.CharField(max_length=20, choices=ProjectMember.Role.choices, help_text="The role they will have in the project.")
    token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_project_invitations')
    
    # This links to the user (either existing, or newly-created-inactive)
    user_to_invite = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='project_invitations')
    
    class Meta:
        # A user can only have one pending invitation for a specific project
        unique_together = ('project', 'email', 'status')
        ordering = ['-created_at']
        
        permissions = [
            ("can_invite_member", "User can send project invitations"),
            ("can_view_invitations", "User can view sent invitations"),
            ("can_cancel_invitation", "User can revoke/cancel pending invitations"),
        ]

    def __str__(self):
        return f"Invitation for {self.email} to join {self.project.name} as {self.role}"