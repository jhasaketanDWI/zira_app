from rest_framework import permissions
from django.core.exceptions import PermissionDenied
from project.models import ProjectMember
from user.models import User

def check_project_permission(user, project, allowed_roles=None):
    """Utility function to check if user has required role for a project."""
    membership = ProjectMember.objects.filter(user=user, project=project).first()

    # This part always runs, checking for basic membership.
    if not membership:
        raise PermissionDenied("You are not a member of this project.")

    # If allowed_roles is None, use the default restrictive roles.
    if allowed_roles is None:
        default_roles = ["OWNER", "PROJECT_MANAGER"]
        if membership.role not in default_roles:
            raise PermissionDenied("You do not have permission to perform this action.")
    elif allowed_roles == []:
        return True
    # If allowed_roles is a non-empty list, check against it.
    elif allowed_roles and membership.role not in allowed_roles:
        raise PermissionDenied("You do not have the required role for this action.")
    return True

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
    # class IsOwnerOrAdmin(BasePermission):
    # def has_permission(self, request, view):
    #     return (
    #         request.user and
    #         request.user.is_authenticated and
    #         request.user.role in [User.Role.OWNER, User.Role.ADMIN]
    #     )

class IsOwnerUser(permissions.BasePermission):
    """
    Custom permission to only allow users with the 'OWNER' role to access a view.
    """
    def has_permission(self, request, view):
        # Check if the user is authenticated and has the role of 'OWNER'
        return request.user and request.user.is_authenticated and request.user.role == User.Role.OWNER
    

class IsOwnerAdminOrManager(permissions.BasePermission):
    """
    Allows access only to Owners, Admins, or Managers.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in [
            User.Role.OWNER, 
            User.Role.ADMIN, 
            User.Role.MANAGER
        ]
    

class IsOwnerAdminOrScrumMaster(permissions.BasePermission):
    """
    Custom permission to only allow users with the global role of
    Owner, Admin, or Scrum Master.
    """
    message = "You do not have permission to create a team. Only Owners, Admins, and Scrum Masters are allowed."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if the user's role is one of the allowed roles [cite: models.py]
        return request.user.role in [
            User.Role.OWNER,
            User.Role.ADMIN,
            User.Role.SCRUM_MASTER
        ]