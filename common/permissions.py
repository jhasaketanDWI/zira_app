from rest_framework import permissions
from django.core.exceptions import PermissionDenied
from project.models import ProjectMember

def check_project_permission(user, project, allowed_roles=None):
    """Utility function to check if user has required role for a project."""
    if allowed_roles is None:
        allowed_roles = ["OWNER", "PROJECT_MANAGER"]

    membership = ProjectMember.objects.filter(user=user, project=project).first()
    if not membership or membership.role not in allowed_roles:
        raise PermissionDenied("You do not have permission to perform this action.")
class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to edit it.
    """

    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner of the account or an admin.
        return obj == request.user or request.user.is_staff
