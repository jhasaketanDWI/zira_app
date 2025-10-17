from rest_framework import permissions
from user.models import User
from common.models import Comment
from task.models import Task
from project.models import ProjectMember
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from common.permissions import check_project_permission

class IsAuthorOrReadOnly(BasePermission):
    """
    Custom permission to only allow authors of an object to edit or delete it.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.author and obj.author.user == request.user
    
class IsProjectMember(BasePermission):
    """
    Checks if the user is a member or owner of the project associated
    with the object being accessed. This permission runs on every request.
    """
    def has_object_permission(self, request, view, obj):
        project = None
        if hasattr(obj, 'project'):
            project = obj.project
        elif hasattr(obj, 'task') and hasattr(obj.task, 'project'):
            project = obj.task.project
        elif isinstance(obj, Comment) and isinstance(obj.content_object, Task):
            project = obj.content_object.project
        
        if not project:
            return False

        try:
            return check_project_permission(request.user, project, allowed_roles=[])
        except PermissionDenied:
            return False


class HasFullTaskAccess(permissions.BasePermission):
    """
    Grants permission to users with 'OWNER' or 'MANAGER' roles.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in [User.Role.OWNER, User.Role.MANAGER]

class CanViewTask(permissions.BasePermission):
    """
    Grants read-only permission to all authenticated users, but full access
    to Owners and Managers.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Allow read-only access (GET, HEAD, OPTIONS) for any authenticated user
        if request.method in permissions.SAFE_METHODS:
            return True

        # For write methods (POST, PUT, DELETE), check for Owner or Manager role
        return request.user.role in [User.Role.OWNER, User.Role.MANAGER]
