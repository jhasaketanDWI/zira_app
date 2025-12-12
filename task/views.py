from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from .models import( Epic, Sprint, Ticket, Task,Activity ,Tag,ActivityLog, Status as StatusModel, Goal,FormTemplate)
from rest_framework import viewsets,status
from common.permissions import check_project_permission,IsOwnerOrAdmin
from .permissions import HasFullTaskAccess, CanViewTask
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.db import transaction
from .permissions import IsProjectMember, IsAuthorOrReadOnly
from rest_framework import serializers
from project.models import Project, ProjectMember
from rest_framework import serializers
from common.models import Comment
from django.contrib.contenttypes.models import ContentType
from rest_framework.exceptions import PermissionDenied
from user.models import User
from .serializers import FormTemplateSerializer, FormSubmissionSerializer,GoalSerializer
from common.permissions import RBACPermission




from .serializers import(
       EpicSerializer,
         SprintSerializer,
         TicketSerializer,
            TagSerializer,
                TaskSerializer, StatusSerializer, TaskStatusUpdateSerializer,
                TaskAssigneesUpdateSerializer, TaskDescriptionUpdateSerializer,
                TaskSubtaskUpdateSerializer, TaskDueDateUpdateSerializer,
                TaskStoryPointsUpdateSerializer, TaskPriorityUpdateSerializer,
                ActivitySerializer,
                TaskSprintUpdateSerializer,
                TaskBoardSerializer,
                CommentSerializer
                )

     
class ActivityViewSet(viewsets.ModelViewSet):
    """
    Manages activities for a specific task.
    """
    queryset = Activity.objects.all()
    serializer_class = ActivitySerializer
    permission_classes = [IsAuthenticated, IsProjectMember]
    def get_queryset(self):
        # Filter activities based on the task_pk from the URL
        return self.queryset.filter(task_id=self.kwargs['task_pk'])

    def perform_create(self, serializer):
        # Automatically associate the activity with the correct task
        task = get_object_or_404(Task, pk=self.kwargs['task_pk'])
        check_project_permission(self.request.user, task.project, allowed_roles=[])

        serializer.save(task=task, actor=self.request.user)

class EpicViewSet(viewsets.ModelViewSet):
    queryset = Epic.objects.all().order_by("-id")
    serializer_class = EpicSerializer
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'create': 'task.can_create_epic',
        'list': 'task.can_view_all_tasks', # Or create specific 'can_view_epics'
        'retrieve': 'task.can_view_all_tasks',
        'update': 'task.can_edit_epic',
        'partial_update': 'task.can_edit_epic',
        'destroy': 'task.can_delete_epic',
    }
    

    def get_queryset(self):
        user = self.request.user
        # Filter sprints belonging to projects where the user is owner or member
        return Epic.objects.filter(
        Q(project__owner=user) | Q(project__projectmember__user=user)
    ).distinct()

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        check_project_permission(self.request.user, project)  # Owner/PM only
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        project = serializer.instance.project
        check_project_permission(self.request.user, project)
        serializer.save(created_by=self.request.user)



class SprintViewSet(viewsets.ModelViewSet):
    queryset = Sprint.objects.all().order_by("-id")
    serializer_class = SprintSerializer
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'create': 'task.can_create_sprint',
        'list': 'task.can_view_all_tasks',
        'retrieve': 'task.can_view_all_tasks',
        'update': 'task.can_edit_sprint',
        'partial_update': 'task.can_edit_sprint',
        'destroy': 'task.can_delete_sprint', # Make sure to add this to models.py if missing

        # Custom Actions
        'activate': 'task.can_start_sprint',
        'end': 'task.can_end_sprint',
        'check_active_sprint': 'task.can_view_all_tasks',
        'dashboard': 'task.can_view_all_tasks',
        'tickets': 'task.can_view_all_tasks',
        
    }
    def get_queryset(self):
        user = self.request.user
        queryset = Sprint.objects.filter(
            Q(project__owner=user) | Q(project__projectmember__user=user)
        ).distinct().order_by("-id")

        if 'project_pk' in self.kwargs:
            queryset = queryset.filter(project_id=self.kwargs['project_pk'])
            
        project_param = self.request.query_params.get('project_id')
        if project_param:
            queryset = queryset.filter(project_id=project_param)

        return queryset

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        check_project_permission(self.request.user, project)
        serializer.save(owner=self.request.user)

    def perform_update(self, serializer):
        project = serializer.instance.project
        check_project_permission(self.request.user, project)
        serializer.save()
   
    @action(detail=False, methods=['get'], url_path='check-active')
    def check_active_sprint(self, request):
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response({"error": "A 'project_id' query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            return Response({"error": "Project not found."}, status=status.HTTP_404_NOT_FOUND)

        # Basic membership check
        check_project_permission(request.user, project, allowed_roles=[])

        active_sprint = Sprint.objects.filter(project=project, is_active=True).first()

        if active_sprint:
            serializer = self.get_serializer(active_sprint)
            return Response({"is_active_sprint": True, "sprint": serializer.data}, status=status.HTTP_200_OK)
        else:
            return Response({"is_active_sprint": False, "sprint": None}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["patch"], url_path='activate')
    def activate(self, request, pk=None):
        """RBAC: tasks.can_start_sprint"""
        sprint = self.get_object()
        check_project_permission(request.user, sprint.project)

        Sprint.objects.filter(project=sprint.project).update(is_active=False)
        sprint.is_active = True
        sprint.save()
        return Response({"status": "Sprint activated successfully."}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=["patch"], url_path='end')
    def end(self, request, pk=None):
        """RBAC: tasks.can_end_sprint"""
        sprint = self.get_object()
        check_project_permission(request.user, sprint.project)

        if sprint.is_ended:
            return Response({"detail": "Sprint is already ended."}, status=status.HTTP_400_BAD_REQUEST)

        unfinished_tasks = sprint.sprint_tasks.exclude(status__title__iexact='Done')
        if unfinished_tasks.exists():
            return Response(
                {"error": "Cannot end sprint while it contains incomplete tasks.", "detail": "Move tasks to backlog first."},
                status=status.HTTP_400_BAD_REQUEST
            )
        sprint.is_active = False
        sprint.is_ended = True
        sprint.save()
        return Response({"status": "Sprint ended successfully."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def tickets(self, request, pk=None):
        sprint = self.get_object()
        check_project_permission(request.user, sprint.project)
        tickets = sprint.tickets.all()
        serializer = TicketSerializer(tickets, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='dashboard')
    def dashboard(self, request):   
        queryset = self.get_queryset()
        project_id = request.query_params.get('project')
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        active_sprints = queryset.filter(is_active=True, is_ended=False)
        upcoming_sprints = queryset.filter(is_active=False, is_ended=False)
        completed_sprints = queryset.filter(is_ended=True)

        response_data = {
            'active_sprints': self.get_serializer(active_sprints, many=True).data,
            'upcoming_sprints': self.get_serializer(upcoming_sprints, many=True).data,
            'completed_sprints': self.get_serializer(completed_sprints, many=True).data
        }
        return Response(response_data, status=status.HTTP_200_OK)

class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    perms_map = {
        'create': 'task.can_create_task', # Tickets are small tasks
        'update': 'task.can_edit_tasks',
        'destroy': 'task.can_delete_task',
        'list': 'task.can_view_all_tasks',
        'retrieve': 'task.can_view_all_tasks',
    }


    def perform_create(self, serializer):
        # Assuming you want to add permission check here as well
        sprint = serializer.validated_data["sprint"]
        check_project_permission(self.request.user, sprint.project)
        serializer.save()
    
    def perform_update(self, serializer):
        sprint = serializer.instance.sprint
        check_project_permission(self.request.user, sprint.project)
        serializer.save()



class TagViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows tags to be viewed or edited.
    Permissions are checked against the associated project.
    """
    queryset = Tag.objects.all().order_by('name')
    serializer_class = TagSerializer
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'create': 'task.can_create_tag',
        'update': 'task.can_manage_tags',
        'partial_update': 'task.can_manage_tags',
        'destroy': 'task.can_delete_tag',
        'list': 'task.can_view_all_tasks',
        'retrieve': 'task.can_view_all_tasks',
    }

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        # Any project member can create tags, adjust permission if needed
        check_project_permission(self.request.user, project, allowed_roles=[])
        serializer.save()

    def perform_update(self, serializer):
        project = serializer.instance.project
        # Any project member can update tags
        check_project_permission(self.request.user, project, allowed_roles=[])
        serializer.save()

    def perform_destroy(self, instance):
        # Only Owner/PM can delete tags
        check_project_permission(self.request.user, instance.project)
        instance.delete()


class GoalViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing Goals.
    """
    queryset = Goal.objects.all().order_by('-id')
    serializer_class = GoalSerializer
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'create': 'task.can_create_goal',
        'update': 'task.can_edit_goal',
        'partial_update': 'task.can_edit_goal',
        'destroy': 'task.can_delete_goal',
        'list': 'task.can_view_goals',
        'retrieve': 'task.can_view_goals',
        'my_goals': 'task.can_view_goals',
        'off_track_goals': 'tasks.can_view_goals',
    }    
    
    def check_user_role(self, user, allowed_roles):
        """
        Determines if the user holds an allowed role for the current project.
        MUST BE CUSTOMIZED based on your ProjectMember model/logic.
        """
        project_pk = self.kwargs.get('project_pk')
        if not project_pk:
            # If no project is specified, assume no high-level project-specific access
            return False 

        # Placeholder: Check if the user's role in the project matches the allowed_roles
        try:
            # You must ensure ProjectMember is correctly imported and linked
            member = ProjectMember.objects.get(user=user, project_id=project_pk)
            return member.role in allowed_roles
        except:
            # Catch all exceptions (like ProjectMember.DoesNotExist) and deny special access
            return False

    def get_queryset(self):
        user = self.request.user
        project_pk = self.kwargs.get('project_pk')

        queryset = Goal.objects.filter(
            Q(project__owner=user) | Q(project__projectmember__user=user)
        ).distinct()

        if project_pk:
            queryset = queryset.filter(project_id=project_pk)

        sprint_id = self.request.query_params.get('sprint_id')
        if sprint_id:
            queryset = queryset.filter(sprint_id=sprint_id)

        if self.request.query_params.get('root_only') == 'true':
            queryset = queryset.filter(parent__isnull=True)

        return queryset.order_by('-id')

    @action(detail=False, methods=['get'], url_path='my-goals')
    def my_goals(self, request, project_pk=None):
        user = request.user
        queryset = self.get_queryset()

        # If user has explicit permission to view all goals (Manager/Owner), show all.
        # Otherwise, filter to goals related to their tasks.
        if not user.has_perm('tasks.can_view_goals'):
            queryset = queryset.filter(
                sprint__sprint_tasks__assignees__user=user
            ).distinct()
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='off-track')
    def off_track_goals(self, request, project_pk=None):
        queryset = self.get_queryset()
        today = timezone.now().date()
        queryset = queryset.filter(sprint__end_date__lt=today)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        project = serializer.validated_data.get("project")
        if not project:
            sprint = serializer.validated_data.get("sprint")
            if sprint: project = sprint.project
        
        if not project:
             raise serializers.ValidationError({"project": "Project is required."})

        check_project_permission(self.request.user, project, allowed_roles=[])
        serializer.save(project=project)

    def perform_update(self, serializer):
        project = serializer.instance.project
        check_project_permission(self.request.user, project, allowed_roles=[])
        serializer.save()
        
    def perform_destroy(self, instance):
        check_project_permission(self.request.user, instance.project)
        instance.delete()
class TaskViewSet(viewsets.ModelViewSet):
    """
    API endpoint for tasks, providing full CRUD functionality.
    Permissions are checked based on the task's project.
    """
    queryset = Task.objects.all().order_by('-id')
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'create': 'task.can_create_task',
        'list': 'task.can_view_all_tasks', # The queryset handles "view own" fallback
        'retrieve': 'task.can_view_all_tasks',
        'update': 'task.can_edit_tasks',
        'partial_update': 'task.can_edit_tasks',
        'destroy': 'task.can_delete_task',

        # Custom Actions
        'create_status': 'task.can_create_status', # Admin only usually
        'update_task_status': 'task.can_change_status',
        'update_status': 'task.can_change_status',
        'update_assignees': 'task.can_assign_task',
        'update_description': 'task.can_edit_tasks',
        'update_priority': 'task.can_change_priority',
        'update_due_date': 'task.can_set_due_date',
        'update_story_points': 'task.can_edit_story_points',
        'set_parent_task': 'task.can_link_tasks', # or edit_tasks
        'add_activity': 'task.can_add_comment',
        'update_activity': 'task.can_add_comment',
        'delete_activity': 'task.can_add_comment',
        'sprint': 'task.can_move_to_backlog', # Moving task to sprint/backlog
        'by_status': 'task.can_view_all_tasks',
    }
    def get_queryset(self):
        user = self.request.user
        queryset = Task.objects.filter(
            Q(project__owner=user) | Q(project__projectmember__user=user)
        ).distinct()

        if 'project_pk' in self.kwargs:
            queryset = queryset.filter(project_id=self.kwargs['project_pk'])

        # RBAC Visibility Check
        if user.has_perm('tasks.can_view_all_tasks'):
            return queryset.order_by('-id')
        
        # Restricted view for roles without full view permission
        return queryset.filter(assignees__user=user).order_by('-id')

    def _update_task_field(self, request, pk, serializer_class):
        task = self.get_object()
        check_project_permission(request.user, task.project, allowed_roles=[])
        serializer = serializer_class(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TaskSerializer(task, context={'request': request}).data, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        project = None
        if 'project_pk' in self.kwargs:
            project = get_object_or_404(Project, pk=self.kwargs['project_pk'])
        else:
            project = serializer.validated_data.get('project')

        if not project:
            raise serializers.ValidationError({"project": "Project not found or not provided."})

        check_project_permission(self.request.user, project, allowed_roles=[])
        
        task_instance = None
        if 'reporter' not in serializer.validated_data:
            reporter = self.request.user.projectmember_set.filter(project=project).first()
            if reporter:
                task_instance = serializer.save(reporter=reporter)
            else:
                task_instance = serializer.save(project=project)
        else:
            task_instance = serializer.save(project=project)

        ActivityLog.objects.create(
            project=project, task=task_instance, user=self.request.user,
            action_type='CREATE', details={'title': task_instance.title}
        )

    def perform_update(self, serializer):
        project = serializer.instance.project
        check_project_permission(self.request.user, project, allowed_roles=[])
        updated_instance = serializer.save()

        ActivityLog.objects.create(
            project=project, task=updated_instance, user=self.request.user,
            action_type='UPDATE', details={'title': updated_instance.title, 'message': 'Task details were updated.'}
        )

    def perform_destroy(self, instance):
        check_project_permission(self.request.user, instance.project)
        instance.delete()
    
    @action(detail=False, methods=['post'], url_path='create-status', permission_classes=[IsAuthenticated, IsAdminUser])
    def create_status(self, request):
        """Usually Admin only, handled by StatusViewSet normally."""
        serializer = StatusSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['patch'], url_path='status')
    def update_task_status(self, request, pk=None):
        """RBAC: tasks.can_change_status"""
        task = self.get_object()
        check_project_permission(self.request.user, task.project, allowed_roles=[])

        serializer = TaskStatusUpdateSerializer(task, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            ActivityLog.objects.create(
                project=task.project, task=task, user=request.user,
                action_type='STATUS_UPDATE',
                details={
                    'title': task.title,
                    'new_status': str(serializer.validated_data.get('status')),
                    'message': f"Task status updated to {serializer.validated_data.get('status')}."
                }
            )
            return Response(TaskSerializer(task).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'], url_path='by-status')
    def by_status(self, request):
        project_id = request.query_params.get('project_id')
        if not project_id:
            return Response({"error": "A 'project_id' query parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            return Response({"error": "Project not found."}, status=status.HTTP_404_NOT_FOUND)

        check_project_permission(request.user, project, allowed_roles=[])

        all_statuses = StatusModel.objects.all().order_by('order')
        project_tasks = Task.objects.filter(project=project).select_related(
            'status', 'reporter__user'
        ).prefetch_related('assignees__user', 'tags')

        tasks_grouped_by_status = {task.status_id: [] for task in project_tasks}
        for task in project_tasks:
            tasks_grouped_by_status[task.status_id].append(task)
        
        response_data = []
        for s in all_statuses:
            tasks_for_this_status = tasks_grouped_by_status.get(s.id, [])
            task_serializer = TaskBoardSerializer(tasks_for_this_status, many=True)
            response_data.append({'id': s.id, 'title': s.title, 'tasks': task_serializer.data})
            
        return Response(response_data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch'], url_path='status')
    def update_status(self, request, pk=None):
        return self._update_task_field(request, pk, TaskStatusUpdateSerializer)

    @action(detail=True, methods=['patch'], url_path='assignees')
    def update_assignees(self, request, pk=None):
        return self._update_task_field(request, pk, TaskAssigneesUpdateSerializer)
        
    @action(detail=True, methods=['patch'], url_path='description')
    def update_description(self, request, pk=None):
        return self._update_task_field(request, pk, TaskDescriptionUpdateSerializer)

    @action(detail=True, methods=['patch'], url_path='parent')
    def set_parent_task(self, request, pk=None):
        return self._update_task_field(request, pk, TaskSubtaskUpdateSerializer)

    @action(detail=True, methods=['patch'], url_path='due-date')
    def update_due_date(self, request, pk=None):
        return self._update_task_field(request, pk, TaskDueDateUpdateSerializer)

    @action(detail=True, methods=['patch'], url_path='story-points')
    def update_story_points(self, request, pk=None):
        return self._update_task_field(request, pk, TaskStoryPointsUpdateSerializer)

    @action(detail=True, methods=['patch'], url_path='priority')
    def update_priority(self, request, pk=None):
        task = self.get_object()
        serializer = TaskPriorityUpdateSerializer(task, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            ActivityLog.objects.create(
                project=task.project, task=task, user=request.user,
                action_type='PRIORITY_UPDATE',
                details={'title': task.title, 'new_priority': str(serializer.validated_data.get('priority'))}
            )
            return Response(TaskSerializer(task).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'], url_path='add-activity')
    def add_activity(self, request, pk=None):
        task = self.get_object()
        check_project_permission(request.user, task.project, allowed_roles=[])
        context = self.get_serializer_context()
        serializer = ActivitySerializer(data=request.data, context=context)
        serializer.is_valid(raise_exception=True)
        serializer.save(task=task)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='activities')
    def activities(self, request, pk=None):
        task = self.get_object()
        activities_with_comments = task.activity_log.filter(comment__isnull=False)
        context = self.get_serializer_context()
        serializer = ActivitySerializer(activities_with_comments, many=True, context=context)
        return Response(serializer.data)

    @action(detail=True, methods=['put'], url_path='update-activity/(?P<activity_id>[^/.]+)')
    def update_activity(self, request, pk=None, activity_id=None):
        task = self.get_object()
        try:
            activity = task.activity_log.get(id=activity_id)
        except Activity.DoesNotExist:
            return Response({'detail': 'Activity not found'}, status=status.HTTP_404_NOT_FOUND)
        check_project_permission(request.user, task.project, allowed_roles=[])
        context = self.get_serializer_context()
        serializer = ActivitySerializer(activity, data=request.data, partial=True, context=context)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=['delete'], url_path='delete-activity/(?P<activity_id>[^/.]+)')
    def delete_activity(self, request, pk=None, activity_id=None):
        task = self.get_object()
        try:
            activity = task.activity_log.get(id=activity_id)
        except Activity.DoesNotExist:
            return Response({'detail': 'Activity not found'}, status=status.HTTP_404_NOT_FOUND)
        activity.delete()
        return Response({'detail': 'Activity deleted successfully'}, status=status.HTTP_204_NO_CONTENT)
    
    @action(detail=True, methods=['patch'], serializer_class=TaskSprintUpdateSerializer)
    def sprint(self, request, pk=None):
        """RBAC: tasks.can_move_to_backlog"""
        task = self.get_object()
        serializer = self.get_serializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TaskSerializer(task).data)


class StatusViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for handling all operations related to Statuses.
    """
    queryset = StatusModel.objects.all().order_by('id')
    serializer_class = StatusSerializer
    permission_classes = [IsAuthenticated, RBACPermission] # Replaced HasFullTaskAccess
    
    perms_map = {
        'create': 'task.can_create_status',
        'update': 'task.can_edit_status',
        'destroy': 'task.can_delete_status',
        'list': 'task.can_view_all_tasks', # Or a specific status permission
        'retrieve': 'task.can_view_all_tasks',
    }


class CommentViewSet(viewsets.ModelViewSet):
    """
    Manages CRUD operations for comments on a specific task.
    Nested under /tasks/{task_pk}/comments/
    """
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated, RBACPermission, IsAuthorOrReadOnly]

    perms_map = {
        'create': 'task.can_add_comment',
        'update': 'task.can_add_comment', # Logic handled by IsAuthorOrReadOnly too
        'partial_update': 'task.can_add_comment',
        'destroy': 'task.can_add_comment',
        'list': 'task.can_view_all_tasks',
        'retrieve': 'task.can_view_all_tasks',
    }
    def get_queryset(self):
        task_pk = self.kwargs['task_pk']
        task_content_type = ContentType.objects.get_for_model(Task)
        return Comment.objects.filter(content_type=task_content_type, object_id=task_pk)

    def perform_create(self, serializer):
        task = get_object_or_404(Task, pk=self.kwargs['task_pk'])
        try:
            project_member_author = ProjectMember.objects.get(
                user=self.request.user,
                project=task.project
            )
        except ProjectMember.DoesNotExist:
            raise PermissionDenied("You are not a member of this project and cannot comment.")
        serializer.save(author=project_member_author, content_object=task)



#  NEW VIEWSET
class FormTemplateViewSet(viewsets.ModelViewSet):
    """
    Endpoints for:
    1. Listing forms (GET /api/projects/{id}/forms/)
    2. Creating forms (POST /api/projects/{id}/forms/)
    3. Updating forms (PUT /api/projects/{id}/forms/{form_id}/)
    4. Deleting forms (DELETE /api/projects/{id}/forms/{form_id}/)
    5. Submitting forms (POST /api/projects/{id}/forms/{form_id}/submit/)
    """
    serializer_class = FormTemplateSerializer
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'create': 'task.can_create_form_template',
        'update': 'task.can_edit_form_template',
        'partial_update': 'task.can_edit_form_template',
        'destroy': 'task.can_delete_form_template',
        'list': 'task.can_view_all_tasks', # Forms are usually visible to team
        'retrieve': 'task.can_view_all_tasks',
        'submit_form': 'task.can_submit_form', # Or can_create_task
    }
    def get_queryset(self):
        # Filter by project from URL
        if 'project_pk' in self.kwargs:
            return FormTemplate.objects.filter(project_id=self.kwargs['project_pk']).order_by('-updated_at')
        return FormTemplate.objects.none()

    def perform_destroy(self, instance):
        check_project_permission(self.request.user, instance.project)
        instance.delete()

    @action(detail=True, methods=['post'], url_path='submit')
    def submit_form(self, request, project_pk=None, pk=None):
        form_template = self.get_object()
        
        serializer = FormSubmissionSerializer(
            data=request.data, 
            context={'request': request, 'form_template': form_template}
        )
        
        if serializer.is_valid():
            task = serializer.save()
            
            # --- GET ASSIGNEE NAMES FOR RESPONSE ---
            assigned_people = [
                {
                    "id": m.id, 
                    "name": m.user.get_full_name() or m.user.username
                } 
                for m in task.assignees.all()
            ]
            
            return Response({
                "message": "Task created successfully.",
                "taskId": task.id,
                "taskTitle": task.title,
                "assignedTo": assigned_people  # <--- Now returns a list of names/objects
            }, status=status.HTTP_201_CREATED)
            
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)