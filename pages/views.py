from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from django.db.models import Q
from django.shortcuts import get_object_or_404

from .models import Page, PageVersion
from .serializers import PageSerializer, PageVersionSerializer
from project.models import Project
from common.permissions import check_project_permission


class PageViewSet(viewsets.ModelViewSet):
    """
    Handles all CRUD for pages (project documentation).
    - /api/pages/               -> all pages current user can see
    - /api/projects/{project_pk}/pages/ -> pages for that project
    """
    queryset = Page.objects.all().order_by("path")
    serializer_class = PageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        qs = Page.objects.filter(
            Q(project__owner=user) | Q(project__projectmember__user=user)
        ).distinct()  # same membership logic as tasks/epics/sprints

        # If nested under a project: /projects/{project_pk}/pages/
        project_pk = self.kwargs.get("project_pk")
        if project_pk is not None:
            qs = qs.filter(project_id=project_pk)

        # Optionally exclude archived by default
        return qs.filter(is_archived=False).select_related("project", "parent")

    def perform_create(self, serializer):
        """
        If nested under /projects/{project_pk}/, take project from URL;
        otherwise require it from payload.
        """
        project = None
        project_pk = self.kwargs.get("project_pk")
        if project_pk is not None:
            project = get_object_or_404(Project, pk=project_pk)
        else:
            project = serializer.validated_data.get("project")

        if not project:
            raise serializers.ValidationError({"project": "Project is required."})

        # Any project member may create pages (you can restrict with allowed_roles if needed)
        check_project_permission(self.request.user, project, allowed_roles=[])

        serializer.save(project=project)

    def perform_update(self, serializer):
        page = self.get_object()
        project = page.project
        check_project_permission(self.request.user, project, allowed_roles=[])
        serializer.save()

    def perform_destroy(self, instance):
        # You might want to be stricter here: only Owner/PM can delete
        check_project_permission(self.request.user, instance.project)
        instance.delete()

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request, pk=None, project_pk=None):
        """
        List all versions of a page.
        GET /pages/{id}/versions/
        or   /projects/{project_pk}/pages/{id}/versions/
        """
        page = self.get_object()
        check_project_permission(request.user, page.project, allowed_roles=[])

        serializer = PageVersionSerializer(page.versions.all(), many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore_version(self, request, pk=None, project_pk=None):
        """
        Restore from an old version by creating a **new** version
        based on that content.
        Body: { "version": 3 }
        """
        page = self.get_object()
        check_project_permission(request.user, page.project, allowed_roles=[])

        version_number = request.data.get("version")
        if version_number is None:
            return Response(
                {"detail": "version is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            source = page.versions.get(version=version_number)
        except PageVersion.DoesNotExist:
            return Response(
                {"detail": "Version not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        latest = page.versions.order_by("-version").first()
        new_version_num = (latest.version if latest else 0) + 1

        PageVersion.objects.create(
            page=page,
            version=new_version_num,
            title=source.title,
            content=source.content,
            edited_by=request.user,
        )

        page.title = source.title
        page.latest_version = new_version_num
        page.save(update_fields=["title", "latest_version"])

        return Response(
            PageSerializer(page, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )
