from rest_framework_nested import routers
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import(
     UserViewSet,
     AdminUserViewSet,
     GoogleLogin,
     UserSignUpView,
    AdminSignUpView,
    MyTokenObtainPairView,
    LogoutView,
    )
# from .views import InviteUserView, SetPasswordView, UserRoleUpdateView <- Uncomment after implementing Invitaitons model

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'admin/users', AdminUserViewSet, basename='admin-user')


# The API URLs are now determined automatically by the router.
urlpatterns = [

    # Custom signup endpoints
    path('signup/user/', UserSignUpView.as_view(), name='user-signup'),
    path('signup/admin/', AdminSignUpView.as_view(), name='admin-signup'),
    
   # JWT Authentication endpoints
    path('token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'), 
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('logout/', LogoutView.as_view(), name='logout'), 

    # Google OAuth API (token-based)
    path('auth/google/', GoogleLogin.as_view(), name='google_login'),

    path('', include(router.urls)),
]

# Keep these urls commented till invitations model is applied
"""# URL for an OWNER to invite a new user
path('users/invite/', InviteUserView.as_view(), name='user-invite'),

# URL for an invited user to set their password
path('users/set-password/', SetPasswordView.as_view(), name='set-password'),

# URL for an OWNER to change a user's role
path('users/<int:pk>/change-role/', UserRoleUpdateView.as_view(), name='user-change-role')"""





