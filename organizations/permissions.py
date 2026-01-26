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

class IsSuperAdminOrOrgOwner(BasePermission):
    """
    Super admins have full access.
    Owners have access ONLY to their own organization.
    """

    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and (
            user.is_super_admin or user.role == "OWNER"
        )

    def has_object_permission(self, request, view, obj):
        user = request.user

        # Super admin → unrestricted
        if user.is_super_admin:
            return True

        # Owner → only their own organization
        return user.role == "OWNER" and user.organization_id == obj.id