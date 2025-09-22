from django.utils.decorators import method_decorator
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import action
from .models import User
from rest_framework import viewsets, permissions, generics,viewsets, status, exceptions
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from common.permissions import IsOwnerOrAdmin

from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import(
     UserSerializer, 
     UserSignUpSerializer,
     AdminSignUpSerializer,
     )

# These imports are required to set up the Google social login endpoint
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView


class UserViewSet(viewsets.ModelViewSet):

    queryset = User.objects.filter(is_staff=False)

    def get_serializer_class(self):
        if self.action == 'create':
            return UserSignUpSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action == 'create':
            self.permission_classes = [AllowAny]
        elif self.action in ['retrieve', 'update', 'partial_update', 'destroy']:
            self.permission_classes = [IsOwnerOrAdmin]
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        response_serializer = UserSerializer(user)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class AdminUserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    permission_classes = [IsAdminUser] # Only admins can access this viewset

    def get_serializer_class(self):
        if self.action == 'create':
            return AdminSignUpSerializer
        return UserSerializer # Use the safe serializer for listing/updating
    
class UserSignUpView(generics.CreateAPIView):
    """
    Public endpoint to register a normal user.
    """
    serializer_class = UserSignUpSerializer
    permission_classes = [AllowAny]

class AdminSignUpView(generics.CreateAPIView):
    """
    Public endpoint to register an admin user.
    """
    serializer_class = AdminSignUpSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"message": "Admin account created successfully. Please login."},
            status=status.HTTP_201_CREATED
        )


@method_decorator(csrf_exempt, name='dispatch')
class GoogleLogin(SocialLoginView):
    """
    This view handles the server-side logic for social authentication with Google.
    The frontend sends a POST request with an access_token or code from Google.
    This view verifies it, creates a new user if they don't exist, and returns
    a JWT (access and refresh tokens) to the client for authenticating future
    API requests.
    """
    adapter_class = GoogleOAuth2Adapter
    client_class = OAuth2Client
    # callback_url = "http://localhost:3000"  # Replace with your frontend URL