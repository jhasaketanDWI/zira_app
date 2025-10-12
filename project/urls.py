from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProjectViewSet, ProjectMemberViewSet, ProjectSummaryView

# This router is imported by the main project urls.py for nesting purposes.
router = DefaultRouter()
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'members', ProjectMemberViewSet, basename='projectmember')

urlpatterns = [
    path('', include(router.urls)),
    path('projects/<int:project_id>/summary/', ProjectSummaryView.as_view(), name='project-summary'),

]

