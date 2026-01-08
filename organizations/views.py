from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count

from .models import Organization
from .serializers import OrganizationSerializer
from .permissions import IsSuperAdmin


class OrganizationViewSet(ReadOnlyModelViewSet):
    """
    Super-admin can view all organizations with summary info.
    """
    serializer_class = OrganizationSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        return (
            Organization.objects.annotate(
                user_count=Count("users", distinct=True),
                project_count=Count("projects", distinct=True),
            )
            .order_by("name")
        )

