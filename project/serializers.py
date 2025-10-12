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

class _UserNestedSerializer(serializers.ModelSerializer):
    """A lightweight, read-only serializer for displaying user details."""
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name']

class _ProjectNestedSerializer(serializers.ModelSerializer):
    """A lightweight, read-only serializer for displaying project details."""
    class Meta:
        model = Project
        fields = ['id', 'name']

class ProjectMemberSerializer(serializers.ModelSerializer):
    # Use the nested serializers for GET requests (read-only)
    user = _UserNestedSerializer(read_only=True)
    project = _ProjectNestedSerializer(read_only=True)

    # Use standard PrimaryKeyRelatedField for POST/PUT requests (write-only)
    # This allows you to still send simple IDs when creating/updating a member.
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='user', write_only=True
    )
    project_id = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(), source='project', write_only=True
    )

    class Meta:
        model = ProjectMember
        # Explicitly list fields to control the output
        fields = ['id', 'user', 'project', 'role', 'user_id', 'project_id']


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

class ProjectSerializer(serializers.ModelSerializer):
    owner = _UserNestedSerializer(read_only=True)
    class Meta:
        model = Project
        fields = ["id", "name", "description", "status", "owner", "created_at", "updated_at"]
        read_only_fields = ["owner"]

    def create(self, validated_data):
        """
        Ensure that the project is always created with the logged-in user as the owner.
        """
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["owner"] = request.user
        return Project.objects.create(**validated_data)

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
    

# The new detailed serializer for the project view.
class ProjectDetailSerializer(serializers.ModelSerializer):
    """
    Provides a detailed, nested view of a single Project.
    """
    members = ProjectMemberSerializer(many=True, read_only=True, source='projectmember_set')
    owner = _UserNestedSerializer(read_only=True)
    
    # Add nested serializers for other related items.
    # Assumes 'related_name' was not set, so we use the Django default '_set'.
    epics = EpicSerializer(many=True, read_only=True, source='epic_set')
    sprints = SprintSerializer(many=True, read_only=True, source='sprint_set')
    tasks = TaskSerializer(many=True, read_only=True) # Assumes related_name='tasks'
    
    # For tickets, which are linked via sprints, we use a SerializerMethodField.
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
    # Add nested serializers if you want user/task details
    user_email = serializers.EmailField(source='user.email', read_only=True)
    task_title = serializers.CharField(source='task.title', read_only=True)

    class Meta:
        model = ActivityLog
        fields = ['id', 'action_type', 'details', 'created_at', 'user_email', 'task_title']