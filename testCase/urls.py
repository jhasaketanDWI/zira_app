from rest_framework.routers import DefaultRouter
from django.urls import path, include
from .views import (
    ModuleViewSet, TestSuiteViewSet, TestCaseViewSet,
    TestRunViewSet, TestExecutionViewSet, TestPlanViewSet, 
    EnvironmentViewSet, TestStepViewSet, TestTemplateViewSet,
    TemplateStepViewSet, AITestScriptViewSet, ai_chat_page
)

# Create a simple router for this app
router = DefaultRouter()

# This registers the endpoint
router.register(r"modules", ModuleViewSet)
router.register(r"suites", TestSuiteViewSet)
router.register(r"cases", TestCaseViewSet)
router.register(r"plans", TestPlanViewSet)
router.register(r"runs", TestRunViewSet)
router.register(r"executions", TestExecutionViewSet)
router.register(r"environments", EnvironmentViewSet)
router.register(r"steps", TestStepViewSet)

# end points for template (optional)
router.register(r"templates", TestTemplateViewSet)
router.register(r"template-steps", TemplateStepViewSet)

# end point for ai
router.register(r"interact", AITestScriptViewSet, basename="ai-interact")


urlpatterns = [
    # Include the simple, non-nested URLs
    path('testcase/', include(router.urls)),

    # AI endpoints
    path('testcase/testing/', ai_chat_page, name='ai-chat-page'),
    
    
]