from django.urls import path
from .views import (
    TimelineDataView,
    EpicDateUpdateView,
    TaskDateUpdateView
)

urlpatterns = [
    # Main endpoint for fetching all timeline data for a project
    path('<int:project_id>/', TimelineDataView.as_view(), name='timeline-data'),

    # Endpoints for updating dates
    # PATCH /api/timeline/epics/1/dates/
    path('epics/<int:pk>/dates/', EpicDateUpdateView.as_view(), name='timeline-epic-dates'),
    # PATCH /api/timeline/tasks/1/dates/
    path('tasks/<int:pk>/dates/', TaskDateUpdateView.as_view(), name='timeline-task-dates'),
]