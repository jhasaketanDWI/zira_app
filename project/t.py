from rest_framework import serializers
from testCase.serializers import TestCaseSerializer 
from task.models import Ticket, ActivityLog
from .models import Project, ProjectMember
from user.models import User
from task.serializers import TaskSerializer, TicketSerializer, EpicSerializer, SprintSerializer

class _UserNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'role']

class _ProjectNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ['id', 'name']

class ProjectMemberSerializer(serializers.ModelSerializer):
    user = _UserNestedSerializer(read_only=True)
    project = _ProjectNestedSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='user', write_only=True
    )
    
    class Meta:
        model = ProjectMember
        fields = ['id', 'user', 'project', 'role', 'user_id']

class ProjectSerializer(serializers.ModelSerializer):
    owner = _UserNestedSerializer(read_only=True)

    # --- ADDED NEW FIELD for assigning a manager during project creation ---
    project_manager_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.MANAGER),
        source='project_manager', # Temporary source name for processing
        write_only=True,
        required=False,
        allow_null=True,
        help_text="ID of the user (with a global 'MANAGER' role) to be assigned as the Project Manager upon creation."
    )
    # --- END OF NEW FIELD ---

    class Meta:
        model = Project
        fields = ["id", "name", "description", "status", "owner", "created_at", "updated_at", "project_manager_id"]
        read_only_fields = ["owner"]

    def create(self, validated_data):
        # The 'project_manager' will be handled in the view's perform_create.
        # We pop it here so it's not passed directly to the Project model's create method.
        validated_data.pop('project_manager', None)
        return super().create(validated_data)

class ProjectDetailSerializer(serializers.ModelSerializer):
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
        tickets = Ticket.objects.filter(sprint__project=project_instance)
        serializer = TicketSerializer(tickets, many=True)
        return serializer.data
    
class ActivityLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    task_title = serializers.CharField(source='task.title', read_only=True)

    class Meta:
        model = ActivityLog
        fields = ['id', 'action_type', 'details', 'created_at', 'user_email', 'task_title']

