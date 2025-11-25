from django.utils.text import slugify
from django.db import transaction
from rest_framework import serializers

from .models import Page, PageVersion
from project.models import Project
from common.permissions import check_project_permission  # reuse your helper


class PageVersionSerializer(serializers.ModelSerializer):
    edited_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = PageVersion
        fields = ["id", "version", "title", "content", "edited_by", "created_at"]


class PageSerializer(serializers.ModelSerializer):
    """
    Main serializer for Page.
    - Accepts `content` when creating/updating -> writes PageVersion
    - Exposes latest_version & latest content on read.
    """
    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=Page.objects.all(),
        source="parent",
        required=False,
        allow_null=True,
        write_only=True,
    )
    parent = serializers.SerializerMethodField(read_only=True)
    content = serializers.CharField(write_only=True, required=False)
    latest_version = serializers.IntegerField(read_only=True)
    latest = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Page
        fields = [
            "id",
            "project",
            "title",
            "slug",
            "parent_id",
            "parent",
            "path",
            "is_archived",
            "latest_version",
            "latest",
            "content",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["project", "slug", "path", "latest_version"]

    def get_parent(self, obj):
        if obj.parent:
            return {
                "id": obj.parent.id,
                "title": obj.parent.title,
            }
        return None

    def get_latest(self, obj):
        """
        Embed a lightweight view of the latest version.
        """
        latest = obj.versions.order_by("-version").first()
        if not latest:
            return None
        return PageVersionSerializer(latest).data

    def _build_unique_slug(self, project: Project, title: str) -> str:
        base_slug = slugify(title) or "page"
        slug = base_slug
        counter = 2
        while Page.objects.filter(project=project, slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug

    def _compute_path(self, project: Project, parent, slug: str) -> str:
        if parent:
            return f"{parent.path}/{slug}"
        # root-level
        return slug

    @transaction.atomic
    def create(self, validated_data):
        """
        Create a Page + its first PageVersion.
        """
        content = validated_data.pop("content", "").strip()
        parent = validated_data.get("parent")
        project = validated_data["project"]
        title = validated_data["title"]

        request = self.context.get("request")
        if request:
            # Ensure user is a member of the project (any role)
            check_project_permission(request.user, project, allowed_roles=[])  #

        slug = self._build_unique_slug(project, title)
        path = self._compute_path(project, parent, slug)

        page = Page.objects.create(
            slug=slug,
            path=path,
            latest_version=1,
            **validated_data,
        )

        PageVersion.objects.create(
            page=page,
            version=1,
            title=title,
            content=content,
            edited_by=request.user if request else None,
        )

        return page

    @transaction.atomic
    def update(self, instance, validated_data):
        """
        Update metadata (title, parent, archive flag) and optionally
        add a new version if content or title changes.
        """
        content = validated_data.pop("content", None)
        old_title = instance.title
        parent = validated_data.get("parent", instance.parent)
        project = instance.project

        request = self.context.get("request")
        if request:
            check_project_permission(request.user, project, allowed_roles=[])  # any project member

        # Update fields on the Page itself
        instance = super().update(instance, validated_data)

        # Recompute path if parent or title changed
        if "parent" in validated_data or "title" in validated_data:
            slug = instance.slug  # keep slug stable; only path reflects tree change
            instance.path = self._compute_path(project, parent, slug)
            instance.save(update_fields=["path"])

        # Decide if we need a new version
        if content is None and "title" not in validated_data:
            # no content/title changes -> no new version
            return instance

        latest = instance.versions.order_by("-version").first()
        new_version = (latest.version if latest else 0) + 1

        PageVersion.objects.create(
            page=instance,
            version=new_version,
            title=instance.title,
            content=content if content is not None else (latest.content if latest else ""),
            edited_by=request.user if request else None,
        )

        instance.latest_version = new_version
        instance.save(update_fields=["latest_version"])

        return instance
