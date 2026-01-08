from rest_framework.permissions import BasePermission

class IsSuperAdmin(BasePermission):
    """
    Allows access only to super admin users.
    """

    def has_permission(self, request, view):
        return bool(
            request.user.is_authenticated and
            getattr(request.user, "is_super_admin", False)
        )
