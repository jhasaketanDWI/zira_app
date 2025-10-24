from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from .models import( Epic, Sprint, Ticket, Task,Activity ,Tag,ActivityLog, Status as StatusModel)
from rest_framework import viewsets,status
from common.permissions import check_project_permission
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

    def get_queryset(self):
        user = self.request.user
        # Filter sprints belonging to projects where the user is owner or member
        return Sprint.objects.filter(
        Q(project__owner=user) | Q(project__projectmember__user=user)
    ).distinct()

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        check_project_permission(self.request.user, project)  # Owner/PM only
        serializer.save()

    def perform_update(self, serializer):
        project = serializer.instance.project
        check_project_permission(self.request.user, project)
        serializer.save()

    @action(detail=True, methods=["patch"],url_path='activate')
    def activate(self, request, pk=None):
        """Custom action to activate a sprint (only one active sprint per project)."""
        sprint = self.get_object()
        check_project_permission(request.user, sprint.project)

        # Deactivate other sprints in the same project
        Sprint.objects.filter(project=sprint.project).update(is_active=False)
        sprint.is_active = True
        sprint.save()

        return Response({"status": "Sprint activated successfully."}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=["patch"],url_path='end')
    def end(self, request, pk=None):
        sprint = self.get_object()
        check_project_permission(request.user, sprint.project)

        if sprint.is_ended:
            return Response({"detail": "Sprint is already ended."}, status=status.HTTP_400_BAD_REQUEST)

        # Find any tasks in this sprint that are NOT in a 'Done' status.
        # The '__iexact' makes the check case-insensitive.
        unfinished_tasks = sprint.sprint_tasks.exclude(status__title__iexact='Done')
        if unfinished_tasks.exists():
            # If any unfinished tasks exist, block the action and return an error.
            return Response(
                {
                    "error": "Cannot end sprint while it contains incomplete tasks.",
                    "detail": "Please move all tasks that are not 'Done' to the backlog or another sprint before proceeding."
                },
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
        """
        Provides a structured list of sprints for the dashboard view.
        You can filter by project by adding a `?project=<project_id>` query parameter.
        """
        queryset = self.get_queryset()

        # Get the project ID from the URL (e.g., /dashboard/?project=1)
        project_id = request.query_params.get('project')
        
        # Correctly filter the queryset if a project ID is provided
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        
        # 1. Active Sprints: Started but not completed
        active_sprints = queryset.filter(is_active=True, is_ended=False)
        
        # 2. Upcoming Sprints: Created but not started or ended
        upcoming_sprints = queryset.filter(is_active=False, is_ended=False)
        
        # 3. Completed Sprints (is_ended=True)
        completed_sprints = queryset.filter(is_ended=True)
        # Serialize the data for the response
        active_serializer = self.get_serializer(active_sprints, many=True)
        upcoming_serializer = self.get_serializer(upcoming_sprints, many=True)
        completed_serializer = self.get_serializer(completed_sprints, many=True)

        
        # Structure the final JSON response with all three sections
        response_data = {
        'active_sprints': active_serializer.data,
        'upcoming_sprints': upcoming_serializer.data,
        'completed_sprints': completed_serializer.data
    }
        
        return Response(response_data, status=status.HTTP_200_OK)

class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer

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


class TaskViewSet(viewsets.ModelViewSet):
    """
    API endpoint for tasks, providing full CRUD functionality.
    Permissions are checked based on the task's project.
    """
    queryset = Task.objects.all().order_by('-id')
    serializer_class = TaskSerializer
    permission_classes = [IsAuthenticated, IsProjectMember]

    def get_queryset(self):
        user = self.request.user
        # Filter sprints belonging to projects where the user is owner or member
        queryset = Task.objects.filter(
        Q(project__owner=user) | Q(project__projectmember__user=user)
    ).distinct()
         # Check if the URL is nested under a project
        if 'project_pk' in self.kwargs:
            project_pk = self.kwargs['project_pk']
            queryset = queryset.filter(project_id=project_pk)

        return queryset
    # --- Helper method for partial updates ---

    def _update_task_field(self, request, pk, serializer_class):
        task = self.get_object()
        
        check_project_permission(request.user, task.project, allowed_roles=[]) # Any project member can update specific fields but it should be done by project owner only
        
        serializer = serializer_class(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TaskSerializer(task, context={'request': request}).data, status=status.HTTP_200_OK)


    def perform_create(self, serializer):
        project = None
        # If called from a nested URL, get the project from the URL
        if 'project_pk' in self.kwargs:
            project_pk = self.kwargs['project_pk']
            project = get_object_or_404(Project, pk=project_pk)
        else:
            # Otherwise, get it from the serializer's validated data
            project = serializer.validated_data.get('project')

        if not project:
            raise serializers.ValidationError({"project": "Project not found or not provided."})

        # Any project member can create tasks
        check_project_permission(self.request.user, project, allowed_roles=[])
        task_instance = None
        # Set the reporter to the current user's project member profile if not provided
        if 'reporter' not in serializer.validated_data:
            reporter = self.request.user.projectmember_set.filter(project=project).first()
            if reporter:
                task_instance = serializer.save(reporter=reporter)
            else: # Fallback if user is not a project member (though permission check should prevent this)
                task_instance = serializer.save(project=project)

        else:
            task_instance = serializer.save(project=project)

        #Track creation activity
        ActivityLog.objects.create(
            project=project,
            task=task_instance,
            user=self.request.user,
            action_type='CREATE',
            details={'title': task_instance.title}
        )


    def perform_update(self, serializer):
        project = serializer.instance.project
        # Any project member can update tasks
        check_project_permission(self.request.user, project, allowed_roles=[])
        original_instance = self.get_object()

        updated_instance=serializer.save()

        
        #Track updated activities
        ActivityLog.objects.create(
            project=project,
            task=updated_instance,
            user=self.request.user,
            action_type='UPDATE',
            details={'title': updated_instance.title, 'message': 'Task details were updated.'}
        )

    def perform_destroy(self, instance):
        # Only Owner/PM can delete tasks
        check_project_permission(self.request.user, instance.project)
        instance.delete()
    
    # Custom action to create a status
    @action(detail=False, methods=['post'], url_path='create-status', permission_classes=[IsAuthenticated, IsAdminUser])
    def create_status(self, request):
        """
        Custom action to create a new status.
        Note: The recommended approach is to use the POST /statuses/ endpoint.
        """
        serializer = StatusSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # Custom action to update only the status of a task
    @action(detail=True, methods=['patch'], url_path='status')
    def update_task_status(self, request, pk=None):
        """
        Custom action to update only the status of a task.
        """
        task = self.get_object()
        # Any project member can update task status
        check_project_permission(self.request.user, task.project, allowed_roles=[])

        serializer = TaskStatusUpdateSerializer(task, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            #Log the status change
            print("Creating ActivityLog...")
            ActivityLog.objects.create(
                project=task.project,
                task=task,
                user=request.user,
                action_type='STATUS_UPDATE',
                details={
                    'title': task.title,
                    'new_status': str(serializer.validated_data.get('status')),
                    'message': f"Task status updated to {serializer.validated_data.get('status')}."
                }
            )
            print("ActivityLog created successfully.")
            # Return the full task data for context
            return Response(TaskSerializer(task).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    
    @action(detail=False, methods=['get'], url_path='by-status')
    def by_status(self, request):
        """
        Retrieves all tasks for a given project, grouped by their status.
        Requires a `project_id` query parameter.
        Example: /api/tasks/by-status/?project_id=1
        """
        project_id = request.query_params.get('project_id')

        if not project_id:
            return Response(
                {"error": "A 'project_id' query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            return Response(
                {"error": "Project not found."},
                status=status.HTTP_404_NOT_FOUND
            )

        check_project_permission(request.user, project, allowed_roles=[])

        all_statuses = StatusModel.objects.all().order_by('order')

        project_tasks = Task.objects.filter(project=project).select_related(
            'status', 'reporter__user'
        ).prefetch_related(
            'assignees__user', 'tags'
        )

        tasks_grouped_by_status = {task.status_id: [] for task in project_tasks}
        for task in project_tasks:
            tasks_grouped_by_status[task.status_id].append(task)
        
        response_data = []
        for s in all_statuses:
            tasks_for_this_status = tasks_grouped_by_status.get(s.id, [])
            task_serializer = TaskBoardSerializer(tasks_for_this_status, many=True)
            
            response_data.append({
                'id': s.id,
                'title': s.title,
                'tasks': task_serializer.data
            })
            
        return Response(response_data, status=status.HTTP_200_OK)

    # --- Custom Actions for Partial Updates ---
    @action(detail=True, methods=['patch'], url_path='status')
    def update_status(self, request, pk=None):
        """PATCH request to update only the task's status."""
        return self._update_task_field(request, pk, TaskStatusUpdateSerializer)

    @action(detail=True, methods=['patch'], url_path='assignees')
    def update_assignees(self, request, pk=None):
        """PATCH request to update only the task's assignees."""
        return self._update_task_field(request, pk, TaskAssigneesUpdateSerializer)
        
    @action(detail=True, methods=['patch'], url_path='description')
    def update_description(self, request, pk=None):
        """PATCH request to update only the task's description."""
        return self._update_task_field(request, pk, TaskDescriptionUpdateSerializer)

    @action(detail=True, methods=['patch'], url_path='parent')
    def set_parent_task(self, request, pk=None):
        """PATCH request to set/unset a task's parent (making it a subtask)."""
        return self._update_task_field(request, pk, TaskSubtaskUpdateSerializer)

    @action(detail=True, methods=['patch'], url_path='due-date')
    def update_due_date(self, request, pk=None):
        """PATCH request to update only the task's due date."""
        return self._update_task_field(request, pk, TaskDueDateUpdateSerializer)

    @action(detail=True, methods=['patch'], url_path='story-points')
    def update_story_points(self, request, pk=None):
        """PATCH request to update only the task's story points."""
        return self._update_task_field(request, pk, TaskStoryPointsUpdateSerializer)

    @action(detail=True, methods=['patch'], url_path='priority')
    def update_priority(self, request, pk=None):
        task = self.get_object()

        # Update the priority
        serializer = TaskPriorityUpdateSerializer(task, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()

            # Log the priority change
            new_priority = serializer.validated_data.get('priority')
            ActivityLog.objects.create(
                project=task.project,
                task=task,
                user=request.user,
                action_type='PRIORITY_UPDATE',
                details={
                    'title': task.title,
                    'new_priority': str(new_priority),
                    'message': f"Task priority updated to {new_priority}."
                }
            )

            # Return the full task data
            return Response(TaskSerializer(task).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'], url_path='add-activity')
    def add_activity(self, request, pk=None):
        """Creates a new comment activity for the task."""
        task = self.get_object()
        check_project_permission(request.user, task.project, allowed_roles=[]) # Any project member can add comment activity
        context = self.get_serializer_context()
        serializer = ActivitySerializer(data=request.data, context=context)
        
        serializer.is_valid(raise_exception=True)
        serializer.save(task=task)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='activities')
    def activities(self, request, pk=None):
        """Fetches the list of all comment activities for the task."""
        task = self.get_object()
        activities_with_comments = task.activity_log.filter(comment__isnull=False)

        context = self.get_serializer_context()
        serializer = ActivitySerializer(activities_with_comments, many=True, context=context)
        
        return Response(serializer.data)

    @action(detail=True, methods=['put'], url_path='update-activity/(?P<activity_id>[^/.]+)')
    def update_activity(self, request, pk=None, activity_id=None):
        """Updates the message of a specific comment."""
        task = self.get_object()
        try:
            activity = task.activity_log.get(id=activity_id)
        except Activity.DoesNotExist:
            return Response({'detail': 'Activity not found'}, status=status.HTTP_404_NOT_FOUND)
        check_project_permission(request.user, task.project, allowed_roles=[]) # Any project member can update comment activity
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
        """
        A dedicated endpoint to update the sprint of a task.
        Accepts PATCH requests to /api/tasks/{id}/sprint/
        """
        task = self.get_object()
        
        #check_project_permission(request.user, task.project) # Any project member can update task sprint
        serializer = self.get_serializer(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        # After updating, return the full task object
        return Response(TaskSerializer(task).data)

class StatusViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for handling all operations related to Statuses.
    """
    queryset = StatusModel.objects.all().order_by('id')
    serializer_class = StatusSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]  # Only admin users can manage statuses for now or else we can authorized a person having Full Task Access



class CommentViewSet(viewsets.ModelViewSet):
    """
    Manages CRUD operations for comments on a specific task.
    Nested under /tasks/{task_pk}/comments/
    """
    serializer_class = CommentSerializer
    permission_classes = [IsAuthenticated, IsProjectMember, IsAuthorOrReadOnly]

    def get_queryset(self):
        """
        Filters the queryset to return only comments belonging to the
        task specified in the URL (e.g., /tasks/123/comments/).
        """
        task_pk = self.kwargs['task_pk']
        # Use Django's ContentType framework to filter comments for the Task model
        task_content_type = ContentType.objects.get_for_model(Task)
        return Comment.objects.filter(content_type=task_content_type, object_id=task_pk)

    def perform_create(self, serializer):
        """
        Automatically associates the new comment with the correct task,
        and sets the author to the correct ProjectMember instance.
        """
        task = get_object_or_404(Task, pk=self.kwargs['task_pk'])

        try:
            # Find the ProjectMember object that links the current user to the task's project.
            project_member_author = ProjectMember.objects.get(
                user=self.request.user,
                project=task.project
            )
        except ProjectMember.DoesNotExist:
            # If no link exists, the user is not a member of this project.
            raise PermissionDenied("You are not a member of this project and cannot comment.")

        # Save the comment, linking it to the ProjectMember and the task.
        serializer.save(author=project_member_author, content_object=task)