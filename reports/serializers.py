from rest_framework import serializers


class ReportsOverviewSerializer(serializers.Serializer):
    """
    Read-only serializer for super admin analytics overview.
    """
    organizations = serializers.IntegerField()
    users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    projects = serializers.IntegerField()
    active_projects = serializers.IntegerField()

class UserActivityReportSerializer(serializers.Serializer):
    """
    Read-only serializer for user activity time-series analytics.
    """
    period = serializers.CharField()
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()

class OngoingProjectReportSerializer(serializers.Serializer):
    """
    Read-only serializer for ongoing projects table in reports.
    """
    project_id = serializers.IntegerField()
    project_name = serializers.CharField()
    organization_name = serializers.CharField()
    project_owner = serializers.CharField()
    status = serializers.CharField()
    last_updated_at = serializers.DateTimeField()

class ProjectProgressReportSerializer(serializers.Serializer):
    """
    Read-only serializer for project task completion analytics.
    """
    project_id = serializers.IntegerField()
    project_name = serializers.CharField()
    completed_tasks = serializers.IntegerField()
    remaining_tasks = serializers.IntegerField()
    total_tasks = serializers.IntegerField()
    completion_percentage = serializers.IntegerField()

class ProjectSummaryReportSerializer(serializers.Serializer):
    """
    Read-only serializer for project summary in reports.
    """
    project_id = serializers.IntegerField()
    project_name = serializers.CharField()
    organization_name = serializers.CharField()
    status = serializers.CharField()
    total_tasks = serializers.IntegerField()
    completed_tasks = serializers.IntegerField()
    last_activity = serializers.DateTimeField(allow_null=True)