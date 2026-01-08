from django.db import models
from django.conf import settings
from common.models import AuditBaseModel
from user.models import User


class Team(AuditBaseModel, models.Model):
    """
    Represents a group of users (a team).
    """
    name = models.CharField(max_length=100, unique=True)
    about = models.TextField(blank=True, null=True, help_text="A description of the team.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='owned_teams'
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='TeamMember',
        related_name='teams',
        through_fields=('team', 'user'),
    )
    class Meta:
        permissions = [
            ("can_create_team", "User can create new teams"),
            ("can_edit_team", "User can update team name and description"),
            ("can_delete_team", "User can delete teams"),
            ("can_view_all_teams", "User can view all teams (Admin view)"),
        ]


    def __str__(self):
        return self.name

class TeamMember(AuditBaseModel, models.Model):
    """
    Links a User to a Team (the "membership").
    This stores their invitation status and their specific role *within* that team.
    """
    class MemberStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='team_memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='team_memberships')

    # This uses your existing User.Role choices [cite: models.py]
    role = models.CharField(
        max_length=50,
        choices=User.Role.choices,
        # This default is just a database-level fallback.
        # The *actual* logic in the serializer is smarter.
        default=User.Role.DEVELOPER
    )

    status = models.CharField(max_length=10, choices=MemberStatus.choices, default=MemberStatus.PENDING)

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_team_invitations'
    )

    class Meta:
        # A user can only be in a team once
        unique_together = ('team', 'user')
        permissions = [
            ("can_invite_team_members", "User can invite new members to the team"),
            ("can_remove_team_members", "User can remove members from the team"),
            ("can_manage_team_roles", "User can change the role of existing team members"),
        ]

    def __str__(self):
        return f"{self.user.email} in {self.team.name} ({self.status})"

