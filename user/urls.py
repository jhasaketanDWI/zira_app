from rest_framework_nested import routers
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import(
     UserViewSet,
     AdminUserViewSet,
     GoogleLogin,
     UserSignUpView,
    AdminSignUpView,
    
    )
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'admin/users', AdminUserViewSet, basename='admin-user')


# The API URLs are now determined automatically by the router.
urlpatterns = [
    path('', include(router.urls)),    

    # Custom signup endpoints
    path('signup/user/', UserSignUpView.as_view(), name='user-signup'),
    path('signup/admin/', AdminSignUpView.as_view(), name='admin-signup'),
    
   # JWT Authentication endpoints
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Google OAuth API (token-based)
    path('auth/google/', GoogleLogin.as_view(), name='google_login'),
]






