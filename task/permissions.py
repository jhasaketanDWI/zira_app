from rest_framework import permissions
from user.models import User

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
