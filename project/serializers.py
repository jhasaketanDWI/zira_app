from rest_framework import serializers
from testCase.serializers import TestCaseSerializer 
from task.models import Ticket, ActivityLog

from .models import (
        Project,    
          ProjectMember,
)
from user.models import User
from task.serializers import TaskSerializer, TicketSerializer, EpicSerializer, SprintSerializer
from task.models import Ticket
from organizations.serializers import OrganizationSerializer

class _UserNestedSerializer(serializers.ModelSerializer):
    """A lightweight, read-only serializer for displaying user details."""
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'role']

class _ProjectNestedSerializer(serializers.ModelSerializer):
    """A lightweight, read-only serializer for displaying project details."""
    class Meta:
        model = Project
        fields = ['id', 'name']

class ProjectMemberSerializer(serializers.ModelSerializer):
    user = _UserNestedSerializer(read_only=True)
    project = _ProjectNestedSerializer(read_only=True)

    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.none(), source='user', write_only=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        project = self.context.get("project")

        if request and project:
            if request.user.is_super_admin:
                self.fields['user_id'].queryset = User.objects.all()
            else:
                self.fields['user_id'].queryset = User.objects.filter(
                    organization=project.organization
                )

    # project_id = serializers.PrimaryKeyRelatedField(
    #     queryset=Project.objects.all(), source='project', write_only=True
    # )

    class Meta:
        model = ProjectMember
        # Explicitly list fields to control the output
        fields = ['id', 'user', 'project', 'role', 'user_id']


    def validate(self, data):
        """
        Check that a user is not being added to the same project twice.
        This prevents the 'unique_together' database constraint from being violated.
        """
        # The `data` will contain 'user' and 'project' from the write_only fields
        user = data.get('user')
        project = data.get('project')
        
        if self.instance: # This is an update, so we don't need to check for uniqueness
            return data

        if ProjectMember.objects.filter(user=user, project=project).exists():
            raise serializers.ValidationError("This user is already a member of this project.")
        
        return data
class ProjectMemberBulkAssignByRoleSerializer(serializers.Serializer):
    """
    Serializer for validating each item in a bulk assignment request.
    This is used for input validation only.
    """
    # user_id = serializers.IntegerField()
    # role = serializers.ChoiceField(choices=ProjectMember.Role.choices)
    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )

    class Meta:
        fields = ['user_id', 'role']

class ProjectSerializer(serializers.ModelSerializer):
    owner = _UserNestedSerializer(read_only=True)
    project_manager_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.MANAGER),
        source='project_manager', # Temporary source name for processing
        write_only=True,
        required=False,
        allow_null=True,
        help_text="ID of the user (with a global 'MANAGER' role) to be assigned as the Project Manager upon creation."
    )
    organization = OrganizationSerializer(read_only=True)
    class Meta:
        model = Project
        fields = ["id", "name", "description", "status", "organization", "owner", "project_manager_id", "created_at", "updated_at"]
        read_only_fields = ["owner"]

    def create(self, validated_data):
        request = self.context.get("request")
        validated_data.pop('project_manager', None)

        # Organization is derived, never from payload
        validated_data["organization"] = request.user.organization

        return super().create(validated_data)

    def validate_owner(self, value):
        """
        Ensure the request.user is the same as the project owner 
        when creating or updating.
        """
        request = self.context.get("request")
        if request and request.method == "POST" and value != request.user:
            raise serializers.ValidationError(
                "You can only create projects as yourself (owner must be you)."
            )
        return value
    

class ProjectDetailSerializer(serializers.ModelSerializer):
    """
    Provides a detailed, nested view of a single Project.
    """
    members = ProjectMemberSerializer(many=True, read_only=True, source='projectmember_set')
    owner = _UserNestedSerializer(read_only=True)
    epics = EpicSerializer(many=True, read_only=True, source='epic_set')
    sprints = SprintSerializer(many=True, read_only=True, source='sprint_set')
    tasks = TaskSerializer(many=True, read_only=True)     
    tickets = serializers.SerializerMethodField()    
    test_cases = TestCaseSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'status', 'owner', 'created_at', 'updated_at',
            'members', 'epics', 'sprints', 'tasks', 'tickets','test_cases'
        ]

    def get_tickets(self, project_instance):
        """
        Gathers all tickets from all sprints within the given project.
        """
        tickets = Ticket.objects.filter(sprint__project=project_instance)
        serializer = TicketSerializer(tickets, many=True)
        return serializer.data
    

class ActivityLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    task_title = serializers.CharField(source='task.title', read_only=True)

    class Meta:
        model = ActivityLog
        fields = ['id', 'action_type', 'details', 'created_at', 'user_email', 'task_title']



class ProjectMemberInviteSerializer(serializers.Serializer):
    """
    Serializer for inviting a new user and assigning them a role in a project.
    """
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=ProjectMember.Role.choices)

    def validate_email(self, value):
        # The view will handle detailed logic for existing vs. new users.
        return value.lower()
