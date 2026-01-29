from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.generics import UpdateAPIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings

from rest_framework.exceptions import PermissionDenied
from project.models import ProjectMember
from task.models import Epic, Task

from .serializers import (
    _TimelineEpicSerializer,
    EpicDateUpdateSerializer,
    TaskDateUpdateSerializer
)

from common.utils.email_service import send_notification_email, get_stakeholders_emails



class TimelineDataView(APIView):
    """
    Handles fetching all timeline data (Epics + Tasks) for a single project.
    GET /api/timeline/?project_id=<ID>
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id=None):
        # 1. Get project_id from the function argument
        # The 'project_id' kwarg is directly available.
        project_pk = project_id

        # 2. Permission Check: Ensure user is a member of the requested project
        if not ProjectMember.objects.filter(project_id=project_pk, user=request.user).exists():
            raise PermissionDenied("You do not have permission to view this project's timeline.")

        # 3. Query and Serialize
        try:
            # Use the correct related_name 'epic_tasks' from your Task model
            project_epics = Epic.objects.filter(project_id=project_pk).prefetch_related('epic_tasks')
            serializer = _TimelineEpicSerializer(project_epics, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error in TimelineDataView: {e}")
            return Response({"error": "An unexpected error occurred."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BaseDateUpdateView(UpdateAPIView):
    """
    Base view for handling date updates with proper permission checks.
    It ensures the user is a member of the project they are editing.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self):
        obj = super().get_object()
        # Both Task and Epic models have a 'project' field
        project = obj.project

        # Check if user is a member of the object's project
        if not ProjectMember.objects.filter(project=project, user=self.request.user).exists():
            raise PermissionDenied("You do not have permission to modify items in this project.")

        # You could add a stricter role check here if needed (e.g., only Owner/Manager)

        return obj

    def perform_update(self, serializer):
        # Automatically set updated_by from AuditBaseModel if it exists
        if hasattr(serializer.instance, 'updated_by'):
            serializer.save(updated_by=self.request.user)
        else:
            serializer.save()


class EpicDateUpdateView(BaseDateUpdateView):
    """
    Handles updating start_date and end_date for a specific Epic.
    PATCH /api/timeline/epics/<int:pk>/dates/
    """
    queryset = Epic.objects.all()
    serializer_class = EpicDateUpdateSerializer
    def perform_update(self, serializer):
        # Capture old values for context
        old_start = serializer.instance.start_date
        old_end = serializer.instance.end_date
        
        super().perform_update(serializer)
        
        epic = serializer.instance
        
        # --- [EMAIL INTEGRATION] Epic Dates Changed ---
        # Notify Project Stakeholders (Owner, Admin, Managers)
        recipients = get_stakeholders_emails(epic.project)
        send_notification_email(
            subject=f"[{epic.project.name}] Timeline Update: {epic.title}",
            recipients=recipients,
            template_path="emails/notification.html",
            context={
                'title': "Epic Timeline Updated",
                'message_body': f"The timeline for Epic '{epic.title}' has been updated.",
                'details': {
                    'Epic': epic.title,
                    'New Start': str(epic.start_date),
                    'New End': str(epic.end_date),
                    'Updated By': self.request.user.get_full_name()
                },
                'action_url': f"{settings.FRONTEND_URL}/projects/{epic.project.id}/timeline"
            }
        )



class TaskDateUpdateView(BaseDateUpdateView):
    """
    Handles updating start_date and due_date for a specific Task.
    PATCH /api/timeline/tasks/<int:pk>/dates/
    """
    queryset = Task.objects.all()
    serializer_class = TaskDateUpdateSerializer
    def perform_update(self, serializer):
        super().perform_update(serializer)
        
        task = serializer.instance
        
        # --- [EMAIL INTEGRATION] Task Dates Changed ---
        # Notify Stakeholders + Assignees
        recipients = get_stakeholders_emails(task.project)
        assignees = task.assignees.values_list('user__email', flat=True)
        recipients.extend(assignees)
        
        send_notification_email(
            subject=f"[{task.project.name}] Schedule Update: {task.title}",
            recipients=recipients,
            template_path="emails/notification.html",
            context={
                'title': "Task Rescheduled",
                'message_body': f"The dates for task '{task.title}' have been updated via the timeline.",
                'details': {
                    'Task': task.title,
                    'New Start': str(task.start_date),
                    'New Due Date': str(task.due_date),
                    'Updated By': self.request.user.get_full_name()
                },
                'action_url': f"{settings.FRONTEND_URL}/projects/{task.project.id}/timeline"
            }
        )

