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
        FormTemplateViewSet,
    )

router = routers.DefaultRouter()
# Register top-level resources
router.register(r'epics', EpicViewSet, basename='epic')
router.register(r'sprints', SprintViewSet, basename='sprint')
router.register(r'statuses', StatusViewSet, basename='status')
router.register(r'tasks', TaskViewSet, basename='task')
router.register(r'tickets', TicketViewSet, basename='ticket')
router.register(r'tags', TagViewSet, basename='tag')

#  Register Forms globally (Optional, but good for direct ID access if needed later)
router.register(r'forms', FormTemplateViewSet, basename='form-template')


# This creates routes like /tasks/{task_pk}/activities/
tasks_router = routers.NestedDefaultRouter(router, r'tasks', lookup='task')
tasks_router.register(r'activities', ActivityViewSet, basename='task-activities')
tasks_router.register(r'comments', CommentViewSet, basename='task-comments') # ✨ ADD THIS LINE

urlpatterns = [
    path('', include(router.urls)),
    path('', include(tasks_router.urls)),
]


# ✨ 3. ADD THIS FUNCTION for Project-Level Nesting
# You must call this from your MAIN urls.py to generate: /api/projects/{pk}/forms/
def get_project_nested_routers(project_router):
    """
    Registers task-related routes that are nested under a project.
    """
    project_router.register(r'epics', EpicViewSet, basename='project-epics')
    project_router.register(r'tags', TagViewSet, basename='project-tags')
    project_router.register(r'tasks', TaskViewSet, basename='project-tasks')
    
    # This enables: GET /api/projects/{pk}/forms/
    project_router.register(r'forms', FormTemplateViewSet, basename='project-forms') 
    
    project_router.register(r'sprints', SprintViewSet, basename='project-sprints')
    
    sprints_router = routers.NestedSimpleRouter(project_router, r'sprints', lookup='sprint')
    sprints_router.register(r'tickets', TicketViewSet, basename='sprint-tickets')
    

    return project_router, sprints_router

