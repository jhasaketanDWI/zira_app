from rest_framework.response import Response
from rest_framework.decorators import action
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from .models import( Epic, Sprint, Ticket, Task, Tag, Status as StatusModel)
from rest_framework import viewsets,status
from common.permissions import check_project_permission
from .permissions import HasFullTaskAccess, CanViewTask

from .serializers import(
       EpicSerializer,
         SprintSerializer,
         TicketSerializer,
            TagSerializer,
                TaskSerializer, StatusSerializer, TaskStatusUpdateSerializer,
                TaskAssigneesUpdateSerializer, TaskDescriptionUpdateSerializer,
                TaskSubtaskUpdateSerializer, TaskDueDateUpdateSerializer,
                TaskStoryPointsUpdateSerializer, TaskPriorityUpdateSerializer,
                ActivitySerializer
                )
                
     


class EpicViewSet(viewsets.ModelViewSet):
    queryset = Epic.objects.all().order_by("-id")
    serializer_class = EpicSerializer

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        check_project_permission(self.request.user, project)  # Owner/PM only
        serializer.save()

    def perform_update(self, serializer):
        project = serializer.instance.project
        check_project_permission(self.request.user, project)
        serializer.save()



class SprintViewSet(viewsets.ModelViewSet):
    queryset = Sprint.objects.all().order_by("-id")
    serializer_class = SprintSerializer

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        check_project_permission(self.request.user, project)  # Owner/PM only
        serializer.save()

    def perform_update(self, serializer):
        project = serializer.instance.project
        check_project_permission(self.request.user, project)
        serializer.save()

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Custom action to activate a sprint (only one active sprint per project)."""
        sprint = self.get_object()
        check_project_permission(request.user, sprint.project)

        # Deactivate other sprints in the same project
        Sprint.objects.filter(project=sprint.project).update(is_active=False)
        sprint.is_active = True
        sprint.save()

        return Response({"status": "Sprint activated successfully."}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=["put"])
    def end(self, request, pk=None):
        sprint = self.get_object()
        check_project_permission(request.user, sprint.project)

        if sprint.is_ended:
            return Response({"detail": "Sprint is already ended."}, status=status.HTTP_400_BAD_REQUEST)

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
 # --- Helper method for partial updates ---
    def _update_task_field(self, request, pk, serializer_class):
        task = self.get_object()
        check_project_permission(request.user, task.project, allowed_roles=[]) # Any project member can update specific fields but it should be done by project owner only
        
        serializer = serializer_class(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(TaskSerializer(task, context={'request': request}).data, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        # Any project member can create tasks
        check_project_permission(self.request.user, project, allowed_roles=[])
        # Set the reporter to the current user's project member profile if not provided
        if 'reporter' not in serializer.validated_data:
            reporter = self.request.user.projectmember_set.filter(project=project).first()
            if reporter:
                serializer.save(reporter=reporter)
            else: # Fallback if user is not a project member (though permission check should prevent this)
                 serializer.save()
        else:
            serializer.save()


    def perform_update(self, serializer):
        project = serializer.instance.project
        # Any project member can update tasks
        check_project_permission(self.request.user, project, allowed_roles=[])
        serializer.save()

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
            # Return the full task data for context
            return Response(TaskSerializer(task).data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
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
        """PATCH request to update only the task's priority."""
        return self._update_task_field(request, pk, TaskPriorityUpdateSerializer)
    
    @action(detail=True, methods=['post'], url_path='add-activity')
    def add_activity(self, request, pk=None):
        task = self.get_object()
        serializer = ActivitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(task=task)
        return Response(TaskSerializer(task, context={'request': request}).data)
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
         # Pass the context here too!
        serializer = self.get_serializer(instance, context={'request': request})
        return Response(serializer.data)

    @action(detail=True, methods=['get'], url_path='activities')
    def activities(self, request, pk=None):
        task = self.get_object()
        serializer = ActivitySerializer(task.activity_log.all(), many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['put'], url_path='update-activity/(?P<activity_id>[^/.]+)')
    def update_activity(self, request, pk=None, activity_id=None):
        task = self.get_object()
        try:
            activity = task.activity_log.get(id=activity_id)
        except Activity.DoesNotExist:
            return Response({'detail': 'Activity not found'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = ActivitySerializer(activity, data=request.data, partial=True)
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
    # @action(detail=True, methods=['post'], url_path='add-activity')
    # def add_activity(self, request, pk=None):
    #     """
    #     POST request to add a new entry to the task's activity history.
    #     """
    #     task = self.get_object()
    #     check_project_permission(request.user, task.project, allowed_roles=[])

    #     # 1. Validate the incoming data for the new entry
    #     entry_serializer = ActivityLogEntrySerializer(data=request.data)
    #     entry_serializer.is_valid(raise_exception=True)

    #     # 2. Construct the new log entry with server-side data
    #     new_entry = {
    #         "user": request.user.get_full_name() or request.user.email,
    #         "timestamp": timezone.now().isoformat(),
    #         **entry_serializer.validated_data
    #     }

    #     # 3. Append the new entry to the existing list and save
    #     task.activity_history.append(new_entry)
    #     task.save(update_fields=['activity_history'])

    #     # 4. Return the full, updated task object
    #     return Response(TaskSerializer(task, context={'request': request}).data)

class StatusViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for handling all operations related to Statuses.
    """
    queryset = StatusModel.objects.all().order_by('id')
    serializer_class = StatusSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]  # Only admin users can manage statuses for now or else we can authorized a person having Full Task Access