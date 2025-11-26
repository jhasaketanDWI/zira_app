from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers
from django.shortcuts import get_object_or_404

import markdown as md
import bleach

from .models import Page, PageVersion, PageAttachment, TaskPageLink
from project.models import Project
from task.models import Task
from common.permissions import check_project_permission  # reuse your permission helper
from django.conf import settings

# ----- sanitization settings -----
ALLOWED_TAGS = bleach.sanitizer.ALLOWED_TAGS.union({
    "p", "pre", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "td", "th",
    "code", "img", "blockquote", "ul", "ol", "li"
})

ALLOWED_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height"],
    "*": ["class", "id"],
}
# consider further restricting ALLOWED_ATTRS in production


def markdown_to_sanitized_html(md_text: str) -> str:
    """
    Convert Markdown -> HTML and sanitize the output.
    """
    # Use extensions similar to what your editor expects
    html = md.markdown(md_text or "", extensions=["fenced_code", "tables", "codehilite"])
    cleaned = bleach.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRS, strip=True)
    return cleaned


# ---------------- PageVersionSerializer ----------------
class PageVersionSerializer(serializers.ModelSerializer):
    edited_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = PageVersion
        fields = [
            "id",
            "version",
            "title",
            "editor_format",
            "content_markdown",
            "content_json",
            "content_html",
            "edited_by",
            "comment",
            "created_at",
        ]
        read_only_fields = ["id", "version", "content_html", "edited_by", "created_at"]


# ---------------- PageAttachmentSerializer ----------------
class PageAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = serializers.StringRelatedField(read_only=True)
    file = serializers.FileField(write_only=True)

    class Meta:
        model = PageAttachment
        fields = [
            "id",
            "page",
            "page_version",
            "file",
            "uploaded_by",
            "original_filename",
            "content_type",
            "size",
            "created_at",
        ]
        read_only_fields = ["id", "uploaded_by", "original_filename", "content_type", "size", "created_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)

        page = validated_data.pop("page", None)
        if not page:
            raise serializers.ValidationError({"page": "Page is required."})

        # Permission check: user must be allowed to add attachments (project member)
        check_project_permission(user, page.project, allowed_roles=[])

        uploaded_file = validated_data.pop("file")
        attachment = PageAttachment.objects.create(
            page=page,
            uploaded_by=user,
            file=uploaded_file,
            original_filename=getattr(uploaded_file, "name", None),
            content_type=getattr(uploaded_file, "content_type", None) or "",
            size=getattr(uploaded_file, "size", None) or 0,
            **validated_data,
        )
        return attachment


# ---------------- TaskPageLinkSerializer ----------------
class TaskPageLinkSerializer(serializers.ModelSerializer):
    linked_by = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = TaskPageLink
        fields = ["id", "task", "page", "linked_by", "note", "created_at"]
        read_only_fields = ["id", "linked_by", "created_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        task = validated_data.get("task")
        page = validated_data.get("page")

        if not task or not page:
            raise serializers.ValidationError("task and page are required")

        # Both task.project and page.project should match OR you may allow cross-project linking (policy)
        if task.project_id != page.project_id:
            raise serializers.ValidationError("Task and Page must belong to the same project.")

        # Permission checks: ensure user can link things in the project
        check_project_permission(user, page.project, allowed_roles=[])

        link = TaskPageLink.objects.create(linked_by=user, **validated_data)
        return link


# ---------------- PageSerializer (main) ----------------
class PageSerializer(serializers.ModelSerializer):
    # incoming write fields
    parent_id = serializers.PrimaryKeyRelatedField(
        queryset=Page.objects.all(), source="parent", required=False, allow_null=True, write_only=True
    )

    # incoming content -> treated as Markdown by default; write-only
    content = serializers.CharField(write_only=True, required=False, allow_blank=True)

    # outgoing helpers
    parent = serializers.SerializerMethodField(read_only=True)
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
        extra_kwargs = {"project": {"required": False}}
        read_only_fields = ["id", "slug", "path", "latest_version", "created_at", "updated_at"]

    def get_parent(self, obj):
        if obj.parent:
            return {"id": obj.parent.id, "title": obj.parent.title}
        return None

    def get_latest(self, obj):
        latest = obj.versions.order_by("-version").first()
        if not latest:
            return None
        return PageVersionSerializer(latest).data

    def validate(self, attrs):
        """
        Ensure parent (if provided) belongs to the same project and no cycles.
        """
        parent = attrs.get("parent", None)
        project = attrs.get("project") or getattr(self.instance, "project", None)

        if parent and project and parent.project_id != project.id:
            raise serializers.ValidationError({"parent_id": "Parent must belong to the same project."})

        # Optional: prevent parent = self or parent chain cycles
        if self.instance and parent:
            if parent.id == self.instance.id:
                raise serializers.ValidationError({"parent_id": "A page cannot be its own parent."})
            # You can implement deeper cycle checks if desired

        return attrs

    def _build_unique_slug(self, project: Project, title: str) -> str:
        base = slugify(title) or "page"
        slug = base
        counter = 2
        while Page.objects.filter(project=project, slug=slug).exists():
            slug = f"{base}-{counter}"
            counter += 1
        return slug

    def _compute_path(self, parent, slug: str) -> str:
        if parent:
            return f"{parent.path}/{slug}"
        return slug

    @transaction.atomic
    def create(self, validated_data):
        """
        Create Page and the initial PageVersion.
        Expected input: { "project": <id>, "title": "...", "content": "markdown...", "parent": <Page or None> }
        """
        request = self.context.get("request")
        user = getattr(request, "user", None)

        project = validated_data.get("project")
        if not project:
            raise serializers.ValidationError({"project": "Project is required."})

        # permission: must be a project member (or owner)
        check_project_permission(user, project, allowed_roles=[])

        title = validated_data.get("title")
        parent = validated_data.get("parent", None)
        content_markdown = validated_data.pop("content", "") or ""

        slug = self._build_unique_slug(project, title)
        path = self._compute_path(parent, slug)

        page = Page.objects.create(
            project=project,
            title=title,
            slug=slug,
            parent=parent,
            path=path,
            latest_version=1,
        )

        # render markdown -> html and sanitize
        content_html = markdown_to_sanitized_html(content_markdown)

        PageVersion.objects.create(
            page=page,
            version=1,
            title=title,
            editor_format=PageVersion.EditorFormat.MARKDOWN,
            content_markdown=content_markdown,
            content_html=content_html,
            edited_by=user,
            comment=None,
        )

        return page

    @transaction.atomic
    def update(self, instance, validated_data):
        """
        Update page metadata and/or add a new PageVersion if content/title changed.
        Partial updates are supported.
        """
        request = self.context.get("request")
        user = getattr(request, "user", None)

        project = instance.project
        check_project_permission(user, project, allowed_roles=[])

        # Extract incoming values (but do not pop them out of validated_data unless needed)
        new_title = validated_data.get("title", instance.title)
        new_parent = validated_data.get("parent", instance.parent)
        incoming_content = validated_data.pop("content", None)  # may be None => no content change

        # Update Page fields (title, parent, is_archived)
        instance.title = new_title
        instance.parent = new_parent
        # If you allow editing is_archived via serializer, it will be in validated_data and super().update handles it
        instance = super().update(instance, validated_data)

        # Recompute path if parent changed (keep slug stable to avoid link rot)
        if instance.parent_id != (new_parent.id if new_parent else None):
            # This case unlikely because we've already set parent above, but recompute to be safe
            instance.path = self._compute_path(new_parent, instance.slug)
            instance.save(update_fields=["path"])

        # Determine whether to create a new version:
        create_new_version = False
        latest = instance.versions.order_by("-version").first()
        current_latest_version = latest.version if latest else 0

        # Title change should be reflected in new version (per your rules). If you prefer title-only not to create version, adjust here.
        if new_title != (latest.title if latest else None):
            create_new_version = True

        if incoming_content is not None:
            # incoming_content is canonical markdown
            create_new_version = True

        if create_new_version:
            new_version_num = current_latest_version + 1
            if incoming_content is None:
                # keep previous content if not provided
                content_markdown = latest.content_markdown if latest else ""
            else:
                content_markdown = incoming_content

            # Render & sanitize markdown -> html if markdown editor
            if content_markdown is not None:
                content_html = markdown_to_sanitized_html(content_markdown)
                editor_format = PageVersion.EditorFormat.MARKDOWN
            else:
                content_html = latest.content_html if latest else ""
                editor_format = latest.editor_format if latest else PageVersion.EditorFormat.MARKDOWN

            PageVersion.objects.create(
                page=instance,
                version=new_version_num,
                title=new_title,
                editor_format=editor_format,
                content_markdown=content_markdown,
                content_html=content_html,
                edited_by=user,
                comment=None,
            )

            instance.latest_version = new_version_num
            instance.save(update_fields=["latest_version"])

        return instance