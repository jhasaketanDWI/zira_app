from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TestCaseViewSet

# Create a simple router for this app
router = DefaultRouter()

# This registers the base /testcases/ endpoint
router.register(r'testcases', TestCaseViewSet, basename='testcase')

urlpatterns = [
    # Include the simple, non-nested URLs
    path('', include(router.urls)),
]