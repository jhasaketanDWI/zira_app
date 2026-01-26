'''from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.db.models import Count

from .models import Organization
from .serializers import OrganizationSerializer
from .permissions import IsSuperAdmin
from user.models import User
from project.models import Project


class OrganizationViewSet(ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        return Organization.objects.annotate(
            user_count=Count("users", distinct=True),
            project_count=Count("projects", distinct=True),
        ).order_by("name")

    # -----------------------------
    # PROTECTION: Prevent unsafe edits
    # -----------------------------
    def perform_update(self, serializer):
        org = self.get_object()

        if org.is_protected:
            raise PermissionDenied("This organization is protected and cannot be modified.")

        serializer.save()

    def perform_destroy(self, instance):
        if instance.is_protected:
            raise PermissionDenied("This organization is protected and cannot be deleted.")

        if instance.users.exists():
            raise ValidationError("Cannot delete organization with active users.")

        if instance.projects.exists():
            raise ValidationError("Cannot delete organization with active projects.")

        instance.delete()

    # -----------------------------
    # ADMIN DASHBOARD ENDPOINTS
    # -----------------------------

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """
        GLOBAL SUPER ADMIN DASHBOARD
        """
        return Response({
            "total_organizations": Organization.objects.count(),
            "active_organizations": Organization.objects.filter(is_active=True).count(),
            "inactive_organizations": Organization.objects.filter(is_active=False).count(),
            "total_users": User.objects.filter(is_deleted=False).count(),
            "total_projects": Project.objects.count(),
            "recent_organizations": list(
                Organization.objects.order_by("-created_at")[:5]
                .values("id", "name", "domain", "created_at")
            ),
        })

    @action(detail=True, methods=["get"], url_path="summary")
    def summary(self, request, pk=None):
        """
        PER-ORGANIZATION DASHBOARD
        """
        org = self.get_object()

        users = org.users.filter(is_deleted=False)
        projects = org.projects.all()

        return Response({
            "organization": org.name,
            "domain": org.domain,
            "created_at": org.created_at,
            "is_active": org.is_active,
            "total_users": users.count(),
            "active_users": users.filter(is_active=True).count(),
            "total_projects": projects.count(),
            "active_projects": projects.exclude(status="ARCHIVED").count(),
            "recent_projects": list(
                projects.order_by("-created_at")[:5].values("id", "name", "created_at")
            ),
            "recent_users": list(
                users.order_by("-created_at")[:5]
                .values("id", "email", "first_name", "last_name", "role", "created_at")
            )
        })
'''

'''from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied
from django.db.models import Count

from .models import Organization
from .serializers import OrganizationSerializer
from .permissions import IsSuperAdminOrOrgOwner


class OrganizationViewSet(ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, IsSuperAdminOrOrgOwner]

    def get_queryset(self):
        user = self.request.user

        # Super admin → all organizations
        if user.is_super_admin:
            return Organization.objects.annotate(
                user_count=Count("users", distinct=True),
                project_count=Count("projects", distinct=True),
            )

        # Owner → only their organization
        if user.role == "OWNER" and user.organization:
            return Organization.objects.filter(
                id=user.organization_id
            ).annotate(
                user_count=Count("users", distinct=True),
                project_count=Count("projects", distinct=True),
            )

        return Organization.objects.none()

    def perform_create(self, serializer):
        # Organization creation via API is still SUPER ADMIN ONLY
        if not self.request.user.is_super_admin:
            raise PermissionDenied("Organizations can only be created during signup or by super admins.")
        serializer.save()

    def perform_update(self, serializer):
        # Object-level permission already enforced
        serializer.save()

    def perform_destroy(self, instance):
        # Object-level permission already enforced
        instance.delete()
'''

from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.db.models import Count

from .models import Organization
from .serializers import OrganizationSerializer
from .permissions import IsSuperAdminOrOrgOwner
from user.models import User
from project.models import Project


class OrganizationViewSet(ModelViewSet):
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, IsSuperAdminOrOrgOwner]

    def get_queryset(self):
        user = self.request.user

        # Super admin → all organizations
        if user.is_super_admin:
            return Organization.objects.annotate(
                user_count=Count("users", distinct=True),
                project_count=Count("projects", distinct=True),
            ).order_by("name")

        # Owner → only their organization
        if user.role == "OWNER" and user.organization:
            return Organization.objects.filter(
                id=user.organization_id
            ).annotate(
                user_count=Count("users", distinct=True),
                project_count=Count("projects", distinct=True),
            )

        return Organization.objects.none()

    def perform_create(self, serializer):
        # Organization creation via API is SUPER ADMIN ONLY
        # Owners create orgs only via signup flow
        if not self.request.user.is_super_admin:
            raise PermissionDenied(
                "Organizations can only be created during signup or by super admins."
            )
        serializer.save()

    # -----------------------------
    # PROTECTION: Prevent unsafe edits
    # -----------------------------
    def perform_update(self, serializer):
        org = self.get_object()

        # Protected organizations cannot be modified
        if org.is_protected and not self.request.user.is_super_admin:
            raise PermissionDenied(
                "This organization is protected and cannot be modified."
            )

        serializer.save()

    def perform_destroy(self, instance):
        # Protected organizations cannot be deleted
        if instance.is_protected:
            raise PermissionDenied(
                "This organization is protected and cannot be deleted."
            )

        # Safety checks before deletion
        if instance.users.exists():
            raise ValidationError(
                "Cannot delete organization with active users."
            )

        if instance.projects.exists():
            raise ValidationError(
                "Cannot delete organization with active projects."
            )

        instance.delete()

    # -----------------------------
    # ADMIN DASHBOARD ENDPOINTS
    # -----------------------------
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """
        GLOBAL SUPER ADMIN DASHBOARD
        """
        if not request.user.is_super_admin:
            raise PermissionDenied("Only super admins can access system stats.")

        return Response({
            "total_organizations": Organization.objects.count(),
            "active_organizations": Organization.objects.filter(is_active=True).count(),
            "inactive_organizations": Organization.objects.filter(is_active=False).count(),
            "total_users": User.objects.filter(is_deleted=False).count(),
            "total_projects": Project.objects.count(),
            "recent_organizations": list(
                Organization.objects.order_by("-created_at")[:5]
                .values("id", "name", "domain", "created_at")
            ),
        })

    @action(detail=True, methods=["get"], url_path="summary")
    def summary(self, request, pk=None):
        """
        PER-ORGANIZATION DASHBOARD
        Accessible by:
        - Super admin (any org)
        - Owner (only their org)
        """
        org = self.get_object()

        users = org.users.filter(is_deleted=False)
        projects = org.projects.all()

        return Response({
            "organization": org.name,
            "domain": org.domain,
            "created_at": org.created_at,
            "is_active": org.is_active,
            "total_users": users.count(),
            "active_users": users.filter(is_active=True).count(),
            "total_projects": projects.count(),
            "active_projects": projects.exclude(status="ARCHIVED").count(),
            "recent_projects": list(
                projects.order_by("-created_at")[:5]
                .values("id", "name", "created_at")
            ),
            "recent_users": list(
                users.order_by("-created_at")[:5]
                .values(
                    "id",
                    "email",
                    "first_name",
                    "last_name",
                    "role",
                    "created_at"
                )
            )
        })