from django.db import models
from django.conf import settings
from django.utils.text import slugify

from common.models import AuditBaseModel
from project.models import Project
from task.models import Task


class Page(AuditBaseModel):
    """
    A documentation page belonging to a project (like Jira 'Pages').

    - Belongs to a Project
    - Can have a parent Page (for hierarchy)
    - `path` stores a slash-separated tree path for easy sorting / navigation
    - `latest_version` points to the latest PageVersion.version
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="pages",
    )
    title = models.CharField(max_length=255)

    # Slug is used in paths / URLs (kept unique per project)
    slug = models.SlugField(max_length=255)

    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )

    path = models.TextField(
        help_text=(
            "Path within the project docs tree, e.g. 'architecture/api-design'. "
            "Used for ordering and building the sidebar tree."
        )
    )

    is_archived = models.BooleanField(default=False)

    # Latest content version number for this page
    latest_version = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("project", "slug")
        ordering = ["path", "id"]

    def __str__(self) -> str:
        return f"{self.project.name} / {self.title}"

    def compute_path(self) -> str:
        """
        Compute the path based on the parent chain and slug.
        Call this from your serializer/service when creating/moving pages.
        """
        if self.parent:
            return f"{self.parent.path}/{self.slug}"
        return self.slug

    def ensure_slug(self):
        """
        Helper to generate a basic slug from the title if missing.
        Uniqueness per project should still be enforced in the serializer/service.
        """
        if not self.slug:
            self.slug = slugify(self.title) or "page"


class PageVersion(AuditBaseModel):
    """
    Immutable snapshot of a Page at a specific version.

    We keep both the canonical source (Markdown or JSON) and a
    pre-rendered, sanitized HTML version for fast rendering & search.
    """

    class EditorFormat(models.TextChoices):
        MARKDOWN = "markdown", "Markdown"
        HTML = "html", "HTML"
        JSON = "json", "JSON (structured editor)"

    page = models.ForeignKey(
        Page,
        on_delete=models.CASCADE,
        related_name="versions",
    )

    version = models.PositiveIntegerField(
        help_text="Monotonically increasing version number (1, 2, 3, ...)."
    )

    title = models.CharField(max_length=255)

    editor_format = models.CharField(
        max_length=20,
        choices=EditorFormat.choices,
        default=EditorFormat.MARKDOWN,
        help_text="Format of the canonical source content.",
    )

    # Canonical source content (only one of these will typically be populated)
    content_markdown = models.TextField(
        null=True,
        blank=True,
        help_text="Raw Markdown source from the editor (if using markdown).",
    )
    content_json = models.JSONField(
        null=True,
        blank=True,
        help_text="Structured JSON document if using a rich editor like TipTap.",
    )

    # Always store a pre-rendered, sanitized HTML version for fast display.
    content_html = models.TextField(
        null=True,
        blank=True,
        help_text="Sanitized HTML rendering of the content for display/search.",
    )

    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="edited_page_versions",
    )

    comment = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Optional edit note / summary of the change.",
    )

    class Meta:
        unique_together = ("page", "version")
        ordering = ["-version"]

    def __str__(self) -> str:
        return f"{self.page.title} v{self.version}"


class PageAttachment(AuditBaseModel):
    """
    File / image attached to a Page, typically via the editor's image upload.

    You can optionally link an attachment to the specific PageVersion
    where it was first referenced.
    """
    page = models.ForeignKey(
        Page,
        on_delete=models.CASCADE,
        related_name="attachments",
    )
    page_version = models.ForeignKey(
        PageVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attachments",
        help_text="The version where this attachment was first added (optional).",
    )

    file = models.FileField(
        upload_to="page_attachments/%Y/%m/",
        help_text="Uploaded file (image, document, etc.)",
    )

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="page_attachments",
    )

    original_filename = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    content_type = models.CharField(
        max_length=100,
        null=True,
        blank=True,
    )
    size = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        help_text="Size in bytes (for limits & display).",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.original_filename or f"Attachment #{self.pk}"


class TaskPageLink(AuditBaseModel):
    """
    Many-to-many style link between a Task and a Page.

    This lets you show "Linked pages" on a task, and "Linked tasks" on a page.
    """
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="page_links",
    )
    page = models.ForeignKey(
        Page,
        on_delete=models.CASCADE,
        related_name="task_links",
    )

    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="task_page_links",
    )

    note = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Optional note about why this task is linked to this page.",
    )

    class Meta:
        unique_together = ("task", "page")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.task_id} ↔ {self.page_id}"
