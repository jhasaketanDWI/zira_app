from django.core.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Q
from .models import( Project,ProjectMember)
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from common.permissions import check_project_permission
from .serializers import(ProjectSerializer, ProjectMemberSerializer, ProjectDetailSerializer,ActivityLogSerializer)
from rest_framework.views import APIView
from task.models import Task, ActivityLog 
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count
class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by("-id")
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated] 

    def get_serializer_class(self):
        # Use the detailed serializer for the 'retrieve' action
        if self.action == 'retrieve':
                return ProjectDetailSerializer
        # return super().get_serializer_class()
        return ProjectSerializer
    def get_queryset(self):
        user=self.request.user
        # Filter projects where the user is the owner OR is listed as a project member.
        # The '.distinct()' is important to prevent duplicates if a user is both
        # the owner and explicitly added as a member.
        return Project.objects.filter(
            Q(owner=user) | Q(projectmember__user=user)
        ).distinct()  
     
    def perform_create(self, serializer):
        project = serializer.save(owner=self.request.user)
        ProjectMember.objects.create(
            user=self.request.user,
            project=project,
            role=ProjectMember.Role.OWNER
        )

    def perform_update(self, serializer):
        project = self.get_object()
        check_project_permission(self.request.user, project) 
        serializer.save()

    def list(self, request, *args, **kwargs):
        user_projects = Project.objects.filter(
            projectmember__user=request.user
        ).distinct().order_by("-id")

        grouped = {
            "planned": [],
            "ongoing": [],
            "delayed": [],
            "completed": [],
            "archived": []
        }

        for project in user_projects:
            data = self.get_serializer(project).data
            status_key = project.status.lower()
            if status_key in grouped:
                grouped[status_key].append(data)

        return Response(grouped)



class ProjectMemberViewSet(viewsets.ModelViewSet):
    queryset = ProjectMember.objects.all().order_by("-id")
    serializer_class = ProjectMemberSerializer

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        check_project_permission(self.request.user, project)  #  OWNER/PM required
        serializer.save()

    def perform_update(self, serializer):
        project = serializer.instance.project
        check_project_permission(self.request.user, project)
        serializer.save()

    def perform_destroy(self, instance):
        check_project_permission(self.request.user, instance.project)
        instance.delete()
class ProjectSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, format=None):
        # Ensure the user is a member of the project they are requesting
        if not ProjectMember.objects.filter(project_id=project_id, user=request.user).exists():
            return Response({"error": "You do not have permission to view this project."}, status=status.HTTP_403_FORBIDDEN)

        # 1. Date range calculations
        today = timezone.now()
        seven_days_ago = today - timedelta(days=7)

        # Base queryset for tasks in the current project
        project_tasks = Task.objects.filter(project_id=project_id)

        # 2. Summary Card Logic
        # For 'completed', we assume a status named 'Done'. Adjust if yours is different.
        completed_tasks_last_7_days = project_tasks.filter(
            status__title__iexact='Done', 
            updated_at__gte=seven_days_ago # Using updated_at as a proxy for completed_at
        ).count()

        summary_cards = {
            'completed': completed_tasks_last_7_days,
            'created': project_tasks.filter(created_at__gte=seven_days_ago).count(),
            'updated': project_tasks.filter(updated_at__gte=seven_days_ago).count(),
            'due_soon': project_tasks.filter(due_date__range=[today, today + timedelta(days=3)]).exclude(status__title__iexact='Done').count()
        }

        # 3. Status Overview Logic
        status_overview = project_tasks.values('status__title').annotate(count=Count('id')).order_by('status__title')

        # 4. Recent Activity Logic
        recent_activities = ActivityLog.objects.filter(project_id=project_id)[:10] # Get last 10 activities

        # 5. Assemble the final response
        response_data = {
            "summary_cards": summary_cards,
            "status_overview": {
                "total": project_tasks.count(),
                "breakdown": list(status_overview)
            },
            "recent_activity": ActivityLogSerializer(recent_activities, many=True).data
        }

        return Response(response_data)