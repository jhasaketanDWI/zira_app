from django.contrib import admin
from django.urls import path, include
from rest_framework_nested import routers

# Import the parent router from the project app so we can nest under it
from project.urls import router as projects_router
from testCase.views import TestCaseViewSet

# --- Nested Routing Setup ---
# This is the central point where we define the relationship:
# "test cases are nested under projects"
testcases_router = routers.NestedDefaultRouter(projects_router, r'projects', lookup='project')
testcases_router.register(r'testcases', TestCaseViewSet, basename='project-testcases')

# --- API URL Patterns ---
# We group all API-related URL includes into a single list for clarity.
# This makes it clear that all these patterns belong under the 'api/' namespace.
api_patterns = [
    # App-specific URLs
    path('', include('user.urls')),
    path('', include('task.urls')),
    path('', include('billing.urls')),
    path('', include('testCase.urls')),
    path('', include('team.urls')),
    path('timeline/', include('timeline.urls')),
    
    
    # Include the nested router for URLs like /projects/{id}/testcases/
    path('', include(testcases_router.urls)),

    # IMPORTANT: Include the parent router last to ensure its URLs are checked after the nested ones.
    path('', include('project.urls')),
]

# --- Main URL Patterns ---
urlpatterns = [
    path('admin/', admin.site.urls),

    # This single, specific path now includes all our API endpoints.
    path('api/', include(api_patterns)),

    # Allauth URLs for handling the backend of social logins (optional but good practice)
    path('accounts/', include('allauth.urls')),
]

