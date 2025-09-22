from django.core.exceptions import PermissionDenied
from rest_framework.response import Response

from .models import( Project,ProjectMember)
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from common.permissions import check_project_permission
from .serializers import(ProjectSerializer, ProjectMemberSerializer)

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by("-id")
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated] 

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

