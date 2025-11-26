from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models import Q

from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import ValidationError

from .models import Page, PageVersion, PageAttachment, TaskPageLink
from .serializers import (
    PageSerializer,
    PageVersionSerializer,
    PageAttachmentSerializer,
    TaskPageLinkSerializer,
)
from project.models import Project
from task.models import Task
from common.permissions import check_project_permission


class PageViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Pages.

    Routes expected:
    - /api/pages/                                (list all pages user can access)
    - /api/pages/{pk}/
    - /api/projects/{project_pk}/pages/          (nested list/create)
    - /api/projects/{project_pk}/pages/{pk}/
    Additional actions:
    - GET  /pages/{pk}/versions/                 -> list versions (also available nested)
    - POST /pages/{pk}/restore/                  -> restore a version (body: { "version": n })
    - POST /pages/{pk}/attachments/              -> upload attachment (multipart/form-data)
    - POST /pages/{pk}/link-task/                -> link a task to a page (body: { "task": <id>, "note": "" })
    """

    queryset = Page.objects.all().select_related("project", "parent")
    serializer_class = PageSerializer
    permission_classes = [IsAuthenticated]


    def get_queryset(self):
        """
        Limit pages to those belonging to projects where user is owner or a ProjectMember.
        If nested under project_pk in the URL, further filter to that project.
        """
        user = self.request.user

        # Use Q objects for a clean OR query
        qs = Page.objects.filter(
            Q(project__owner=user) | Q(project__projectmember__user=user)
        )

        project_pk = self.kwargs.get("project_pk")
        if project_pk is not None:
            qs = qs.filter(project_id=project_pk)

        # Exclude archived by default (frontend may want archived in separate call)
        qs = qs.filter(is_archived=False)

        return qs.distinct().select_related("project", "parent")

    def perform_create(self, serializer):
        """
        If nested under /projects/{project_pk}/, take project from URL.
        Otherwise require project in payload.
        Also enforce project permission for creation.
        """
        request = self.request
        user = request.user
        project_pk = self.kwargs.get("project_pk")

        if project_pk is not None:
            project = get_object_or_404(Project, pk=project_pk)
        else:
            # serializer.validated_data.get('project') should be a Project instance
            project = serializer.validated_data.get("project")
            if project is None:
                raise ValidationError({"project": "Project is required."})

        # permission: ensure user is allowed to create pages in project (adjust roles if needed)
        check_project_permission(user, project, allowed_roles=[])

        # save with project enforced from URL/pick
        serializer.save(project=project)

    def perform_update(self, serializer):
        """
        Permission check before updating.
        """
        request = self.request
        user = request.user
        instance = self.get_object()
        check_project_permission(user, instance.project, allowed_roles=[])
        serializer.save()

    def perform_destroy(self, instance):
        """
        Permission check before deleting a page.
        Consider restricting deletion to project owners/managers.
        """
        request = self.request
        user = request.user
        # If you want stricter control change allowed_roles argument
        check_project_permission(user, instance.project, allowed_roles=[])
        instance.delete()

    @action(detail=True, methods=["get"], url_path="versions")
    def versions(self, request, pk=None, project_pk=None):
        """
        List all versions of a page.
        GET /pages/{id}/versions/  (or nested under project)
        """
        page = self.get_object()
        # permission: user must be able to view the project/page
        check_project_permission(request.user, page.project, allowed_roles=[])
        versions = page.versions.all().order_by("-version")
        serializer = PageVersionSerializer(versions, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None, project_pk=None):
        """
        Restore an older version by creating a NEW version from it.
        Body: { "version": 3 }
        """
        page = self.get_object()
        check_project_permission(request.user, page.project, allowed_roles=[])

        version_num = request.data.get("version")
        if version_num is None:
            return Response({"detail": "version is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            source_ver = page.versions.get(version=version_num)
        except PageVersion.DoesNotExist:
            return Response({"detail": "version not found."}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            latest = page.versions.order_by("-version").first()
            new_version_num = (latest.version if latest else 0) + 1

            PageVersion.objects.create(
                page=page,
                version=new_version_num,
                title=source_ver.title,
                editor_format=source_ver.editor_format,
                content_markdown=source_ver.content_markdown,
                content_json=source_ver.content_json,
                content_html=source_ver.content_html,
                edited_by=request.user,
                comment=f"Restored from v{version_num}",
            )

            page.title = source_ver.title
            page.latest_version = new_version_num
            page.save(update_fields=["title", "latest_version"])

        return Response(
            PageSerializer(page, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="attachments", parser_classes=[MultiPartParser, FormParser])
    def upload_attachment(self, request, pk=None, project_pk=None):
        """
        Upload an attachment (image/file) for a page.
        Expects multipart/form-data with 'file' field.
        Returns attachment data including the file URL.
        """
        page = self.get_object()
        check_project_permission(request.user, page.project, allowed_roles=[])

        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"detail": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        data = {
            "page": page.id,
            "file": file_obj,
        }
        serializer = PageAttachmentSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        attachment = serializer.save()

        # Return created attachment with helpful fields (including file URL)
        out = PageAttachmentSerializer(attachment, context={"request": request}).data
        return Response(out, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="link-task")
    def link_task(self, request, pk=None, project_pk=None):
        """
        Link a Task to this Page.
        Body: { "task": <task_id>, "note": "optional note" }
        """
        page = self.get_object()
        check_project_permission(request.user, page.project, allowed_roles=[])

        task_id = request.data.get("task")
        if not task_id:
            return Response({"detail": "task is required."}, status=status.HTTP_400_BAD_REQUEST)

        task = get_object_or_404(Task, pk=task_id)

        # Enforce same-project linking (policy), adjust if you want cross-project links:
        if task.project_id != page.project_id:
            return Response({"detail": "Task and Page must belong to the same project."}, status=status.HTTP_400_BAD_REQUEST)

        data = {
            "task": task.id,
            "page": page.id,
            "note": request.data.get("note", ""),
        }
        serializer = TaskPageLinkSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        link = serializer.save()

        return Response(TaskPageLinkSerializer(link).data, status=status.HTTP_201_CREATED)