from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import(
       EpicViewSet, 
      SprintViewSet,
        TicketViewSet,
        TaskViewSet,
        StatusViewSet
    )



router = DefaultRouter()

router.register(r"epics", EpicViewSet, basename='epic')
router.register(r"sprints", SprintViewSet, basename='sprint')
router.register(r'statuses', StatusViewSet, basename='status')
router.register(r"tasks", TaskViewSet, basename='task')
router.register(r"tickets", TicketViewSet, basename='ticket')

# The API URLs are now determined automatically by the router.
urlpatterns = [
    path('', include(router.urls)),
    
  
]




