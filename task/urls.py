from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers
from .views import(
       EpicViewSet, 
      SprintViewSet,
        TicketViewSet,
        TaskViewSet,
        StatusViewSet,
        TagViewSet,
        ActivityViewSet,
        CommentViewSet,  
    )

router = routers.DefaultRouter()
# Register top-level resources
router.register(r'epics', EpicViewSet, basename='epic')
router.register(r'sprints', SprintViewSet, basename='sprint')
router.register(r'statuses', StatusViewSet, basename='status')
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'tickets', TicketViewSet, basename='ticket')
router.register(r'tags', TagViewSet, basename='tag')


# This creates routes like /tasks/{task_pk}/activities/
tasks_router = routers.NestedDefaultRouter(router, r'tasks', lookup='task')
tasks_router.register(r'activities', ActivityViewSet, basename='task-activities')
tasks_router.register(r'comments', CommentViewSet, basename='task-comments') # ✨ ADD THIS LINE

urlpatterns = [
    path('', include(router.urls)),
    path('', include(tasks_router.urls)),
]




# # task/urls.py

# from rest_framework_nested import routers
# from .views import EpicViewSet, SprintViewSet, StatusViewSet, TaskViewSet, TagViewSet, TicketViewSet

# # router global resources not tied to a specific project
# router = routers.DefaultRouter()
# router.register(r'statuses', StatusViewSet, basename='status')

# # This function will be called from your project's main urls.py
# def get_project_nested_routers(project_router):
#     """
#     Registers task-related routes that are nested under a project.
#     Generates URLs like:
#     - /projects/{project_pk}/tasks/
#     - /projects/{project_pk}/sprints/
#     - /projects/{project_pk}/sprints/{sprint_pk}/tickets/
#     """
    
#     project_router.register(r'epics', EpicViewSet, basename='project-epics')
#     project_router.register(r'tags', TagViewSet, basename='project-tags')
#     project_router.register(r'tasks', TaskViewSet, basename='project-tasks')
    
#     # Create a router for sprints nested under a project
#     sprints_router = routers.NestedSimpleRouter(project_router, r'sprints', lookup='sprint')
#     # Nest tickets under the sprints router
#     sprints_router.register(r'tickets', TicketViewSet, basename='sprint-tickets')
    
#     # Register the main sprints endpoint under the project
#     project_router.register(r'sprints', SprintViewSet, basename='project-sprints')

#     # Return both routers so they can be included in the main URL patterns
#     return project_router, sprints_router
