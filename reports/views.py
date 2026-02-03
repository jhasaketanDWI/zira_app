from datetime import timedelta

from django.utils import timezone
from django.db.models import Q, Count
from django.db.models.functions import TruncMonth, TruncWeek, TruncDay
from django.utils.dateparse import parse_date
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from reports.permissions import IsSuperAdmin
from reports.serializers import (ReportsOverviewSerializer,
                                 UserActivityReportSerializer,
                                 OngoingProjectReportSerializer,
                                 ProjectProgressReportSerializer,
                                 ProjectSummaryReportSerializer,)
from project.serializers import ProjectSerializer

from organizations.models import Organization
from user.models import User
from project.models import Project
from task.models import Task, ActivityLog


class ReportsOverviewView(APIView):
    """
    Provides high-level analytics overview for super admins.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        now = timezone.now()
        active_since = now - timedelta(days=30)

        data = {
            "organizations": Organization.objects.count(),
            "users": User.objects.count(),
            "active_users": User.objects.filter(
                last_login__gte=active_since
            ).count(),
            "projects": Project.objects.count(),
            "active_projects": Project.objects.filter(
                ~Q(status__iexact="archived")
            ).count(),
        }

        serializer = ReportsOverviewSerializer(data)
        return Response(serializer.data)

class UserActivityReportView(APIView):
    """
    Provides total vs active users over time for super admins.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        start_date = parse_date(request.query_params.get("from"))
        end_date = parse_date(request.query_params.get("to"))
        interval = request.query_params.get("interval", "month")

        if not start_date or not end_date:
            return Response(
                {"error": "Both 'from' and 'to' dates are required."},
                status=400
            )

        if interval == "day":
            trunc_func = TruncDay
        elif interval == "week":
            trunc_func = TruncWeek
        else:
            trunc_func = TruncMonth  # default

        # Total users created in each period
        total_users_qs = (
            User.objects
            .filter(created_at__date__range=[start_date, end_date])
            .annotate(period=trunc_func("created_at"))
            .values("period")
            .annotate(total_users=Count("id"))
        )

        # Active users (based on last_login)
        active_users_qs = (
            User.objects
            .filter(last_login__date__range=[start_date, end_date])
            .annotate(period=trunc_func("last_login"))
            .values("period")
            .annotate(active_users=Count("id"))
        )

        # Merge results by period
        data_map = {}

        for row in total_users_qs:
            period = row["period"].strftime("%Y-%m")
            data_map.setdefault(period, {}).update({
                "period": period,
                "total_users": row["total_users"],
                "active_users": 0
            })

        for row in active_users_qs:
            period = row["period"].strftime("%Y-%m")
            data_map.setdefault(period, {}).update({
                "period": period,
                "total_users": 0,
                "active_users": row["active_users"]
            })

        result = list(data_map.values())
        result.sort(key=lambda x: x["period"])

        serializer = UserActivityReportSerializer(result, many=True)
        return Response(serializer.data)

class OngoingProjectsReportView(APIView):
    """
    Provides a read-only, cross-organization list of ongoing projects
    for super admin reporting.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 10))
            offset = int(request.query_params.get("offset", 0))
        except ValueError:
            return Response(
                {"error": "limit and offset must be integers"},
                status=400
            )

        status_filter = request.query_params.get("status")

        qs = (
            Project.objects
            .select_related("organization")
            .order_by("-updated_at")
        )

        if status_filter:
            qs = qs.filter(status__iexact=status_filter)

        total_count = qs.count()

        qs = qs[offset: offset + limit]

        results = [
            {
                "project_id": project.id,
                "project_name": project.name,
                "organization_name": project.organization.name,
                "project_owner": project.owner.first_name + ' ' + project.owner.last_name,
                "status": project.status,
                "last_updated_at": project.updated_at,
            }
            for project in qs
        ]

        serializer = OngoingProjectReportSerializer(results, many=True)

        return Response({
            "count": total_count,
            "results": serializer.data
        })

class ProjectProgressReportView(APIView):
    """
    Provides completed vs remaining task statistics for a project.
    Super admin only, read-only.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request, project_id):
        project = get_object_or_404(Project, pk=project_id)

        total_tasks = Task.objects.filter(project=project).count()

        completed_tasks = Task.objects.filter(
            project=project,
            status__title__iexact="Done"
        ).count()

        remaining_tasks = total_tasks - completed_tasks

        completion_percentage = (
            int((completed_tasks / total_tasks) * 100)
            if total_tasks > 0 else 0
        )

        data = {
            "project_id": project.id,
            "project_name": project.name,
            "completed_tasks": completed_tasks,
            "remaining_tasks": remaining_tasks,
            "total_tasks": total_tasks,
            "completion_percentage": completion_percentage,
        }

        serializer = ProjectProgressReportSerializer(data)
        return Response(serializer.data)

class ProjectSummaryReportView(APIView):
    """
    Read-only project summary for super admin reports.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request, project_id):
        project = get_object_or_404(
            Project.objects.select_related("organization"),
            pk=project_id
        )

        total_tasks = Task.objects.filter(project=project).count()
        completed_tasks = Task.objects.filter(
            project=project,
            status__title__iexact="Done"
        ).count()

        last_activity = (
            ActivityLog.objects
            .filter(project=project)
            .order_by("-created_at")
            .values_list("created_at", flat=True)
            .first()
        )

        data = {
            "project_id": project.id,
            "project_name": project.name,
            "organization_name": project.organization.name,
            "status": project.status,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "last_activity": last_activity,
        }

        serializer = ProjectSummaryReportSerializer(data)
        return Response(serializer.data)

class SuperAdminProjectsReportView(APIView):
    """
    Super admin only:
    Fetch all projects across all organizations.
    Read-only endpoint for admin dashboards & reports.
    """

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request, *args, **kwargs):
        projects = (
            Project.objects
            .select_related("organization", "owner")
            .all()
            .order_by("-created_at")
        )

        serializer = ProjectSerializer(projects, many=True)
        return Response(serializer.data)