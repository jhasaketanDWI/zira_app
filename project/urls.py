from django.urls import path, include
from rest_framework_nested import routers
from .views import ProjectViewSet, ProjectMemberViewSet, ProjectSummaryView, ManagedTeamMembersView
from task.views import TaskViewSet

# This router is imported by the main project urls.py for nesting purposes.
router = routers.DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'members', ProjectMemberViewSet, basename='projectmember')

projects_router = routers.NestedSimpleRouter(router, r'projects', lookup='project')
projects_router.register(r'tasks', TaskViewSet, basename='project-tasks')
projects_router.register(r'members', ProjectMemberViewSet, basename='project-members')



urlpatterns = [
    path('', include(router.urls)),
    path('', include(projects_router.urls)),
    path('projects/<int:project_id>/summary/', ProjectSummaryView.as_view(), name='project-summary'),
    path('managed-team-members/', ManagedTeamMembersView.as_view(), name='managed-team-members'),


]

