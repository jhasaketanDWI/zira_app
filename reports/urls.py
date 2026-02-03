from django.urls import path
from reports.views import (
    ReportsOverviewView,
    UserActivityReportView,
    OngoingProjectsReportView,
    ProjectProgressReportView,
    ProjectSummaryReportView,
    SuperAdminProjectsReportView,
)

urlpatterns = [
    path("overview/", ReportsOverviewView.as_view(), name="reports-overview"),
    path("users/activity/", UserActivityReportView.as_view(), name="reports-user-activity"),
    path("projects/ongoing/", OngoingProjectsReportView.as_view(), name="reports-ongoing-projects"),
    path(
        "projects/<int:project_id>/progress/",
        ProjectProgressReportView.as_view(),
        name="reports-project-progress",
    ),
    path(
        "projects/<int:project_id>/summary/",
        ProjectSummaryReportView.as_view(),
        name="reports-project-summary",
    ),
    path(
        "projects/",
        SuperAdminProjectsReportView.as_view(),
        name="reports-superadmin-projects",
    ),
]