from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    """
    Allows access only to super admins.
    This permission is intentionally strict because reports
    are cross-organization and read-only.
    """

    def has_permission(self, request, view):
        user = request.user

        if not user or not user.is_authenticated:
            return False

        # Allow Django superusers (admin panel users)
        if getattr(user, "is_superuser", False):
            return True

        # Allow application-level super admins
        if getattr(user, "is_super_admin", False):
            return True

        return False