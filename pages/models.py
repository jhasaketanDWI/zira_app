from django.db import models
from django.utils.text import slugify
from django.conf import settings

from common.models import AuditBaseModel
from project.models import Project


class Page(AuditBaseModel):
    """
    A documentation page belonging to a project (like Jira 'Pages').
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="pages",
    )
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    path = models.TextField(
        help_text="Path within the project docs tree, e.g. 'root/architecture/api-design'"
    )
    is_archived = models.BooleanField(default=False)
    latest_version = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("project", "slug")

    def __str__(self):
        return f"{self.project.name} / {self.title}"

    def compute_path(self):
        """
        Build a simple slash-separated path from parent chain.
        """
        if self.parent:
            return f"{self.parent.path}/{self.slug}"
        return self.slug  # root-level


class PageVersion(AuditBaseModel):
    """
    Snapshot of a Page at a given version.
    """
    page = models.ForeignKey(
        Page,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version = models.PositiveIntegerField()
    title = models.CharField(max_length=255)
    content = models.TextField()  # You can later switch to JSONField if you adopt a rich editor

    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edited_page_versions",
    )

    class Meta:
        unique_together = ("page", "version")
        ordering = ["-version"]

    def __str__(self):
        return f"{self.page.title} v{self.version}"