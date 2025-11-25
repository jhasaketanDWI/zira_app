from django.urls import path, include
from rest_framework_nested import routers

from .views import PageViewSet

# Top-level router (optional but handy)
router = routers.DefaultRouter()
router.register(r'pages', PageViewSet, basename='page')

# We'll also define a nested router in config/urls.py, similar to testCase.
urlpatterns = [
    path('', include(router.urls)),
]