from rest_framework_nested import routers
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import(
     UserViewSet,
     AdminUserViewSet,
     GoogleLogin,
     UserSignUpView,
    AdminSignUpView,
    ProjectViewSet, 
    TestCaseViewSet,
    SubscriptionPlanViewSet,
    SubscriptionViewSet,
    InvoiceViewSet,
    ProjectViewSet,
      ProjectMemberViewSet, 
      EpicViewSet, 
      SprintViewSet,
      TicketViewSet
    )
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'admin/users', AdminUserViewSet, basename='admin-user')
router.register(r'projects', ProjectViewSet, basename='project')
router.register(r'testcases', TestCaseViewSet, basename='testcase') 
router.register(r'subscription-plans', SubscriptionPlanViewSet, basename='subscription-plan')
router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r"members", ProjectMemberViewSet,basename='projectmember')
router.register(r"epics", EpicViewSet, basename='epic')
router.register(r"sprints", SprintViewSet, basename='sprint')
router.register(r"tickets", TicketViewSet, basename='ticket')

# Create a nested router for test cases under projects
# This will generate URLs like: /projects/{project_pk}/testcases/
projects_router = routers.NestedDefaultRouter(router, r'projects', lookup='project')
projects_router.register(r'testcases', TestCaseViewSet, basename='project-testcases')

# The API URLs are now determined automatically by the router.
urlpatterns = [
    path('', include(router.urls)),
    path('', include(projects_router.urls)),  
    
    # Custom signup endpoints
    path('signup/user/', UserSignUpView.as_view(), name='user-signup'),
    path('signup/admin/', AdminSignUpView.as_view(), name='admin-signup'),
    
    # JWT Auth
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Google OAuth API (token-based)
    path('auth/google/', GoogleLogin.as_view(), name='google_login'),
]






