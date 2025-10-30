from rest_framework.permissions import BasePermission
from team.models import TeamMember
from user.models import User
class IsTeamAdmin(BasePermission):
    """
    Allows access only to users who are 'ACCEPTED' members and
    have the 'ADMIN' role within that specific team.
    """
    message = "You must be an Admin of this team to perform this action."

    def has_object_permission(self, request, view, obj):
        # 'obj' here is the Team instance
        try:
            membership = TeamMember.objects.get(
                team=obj,
                user=request.user
            )
        except TeamMember.DoesNotExist:
            return False

        return (
            membership.status == TeamMember.MemberStatus.ACCEPTED and
            membership.role == User.Role.ADMIN
        )