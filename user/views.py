from django.utils.decorators import method_decorator
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from .models import User,Invitation
from rest_framework import viewsets, permissions, generics,viewsets, status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from common.permissions import IsOwnerOrAdmin
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import MyTokenObtainPairSerializer
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from django.core.mail import send_mail
from common.permissions import IsOwnerUser,IsOwnerOrAdmin
from django.utils.crypto import get_random_string
from .serializers import(
     UserSerializer, 
     UserSignUpSerializer,
     AdminSignUpSerializer,
     AdminUserManagementSerializer,
     InvitationSerializer, SetPasswordSerializer, UserRoleSerializer
     )
from project.models import Project

# These imports are required to set up the Google social login endpoint
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework.decorators import action

class UserViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for OWNERs and ADMINs to view, create, and edit all users.
    """
    queryset = User.objects.all().order_by('-id').filter(is_deleted=False)
    
    permission_classes = [IsOwnerOrAdmin,IsAuthenticated]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AdminUserManagementSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        response_serializer = UserSerializer(user)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'],url_path='deactivate-user')
    def deactivate(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response({'status': 'user deactivated'})

    @action(detail=True, methods=['patch'],url_path='activate-user')
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response({'status': 'user activated'})




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
            {"message": "Owner account created successfully. Please login."},
            status=status.HTTP_201_CREATED
        )



class TeamStatsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, *args, **kwargs):
        total_members = User.objects.count()
        active_members = User.objects.filter(is_active=True).count()
        
        
        active_projects = Project.objects.exclude(
            status__in=[Project.Status.COMPLETED, Project.Status.ARCHIVED]
        ).count()

        stats = {
            'total_members': total_members,
            'active_members': active_members,
            'active_projects': active_projects
        }
        return Response(stats)

class MyTokenObtainPairView(TokenObtainPairView):
    """
    Custom view for obtaining a token pair that also updates the last_login time.
    """
    serializer_class = MyTokenObtainPairSerializer

class LogoutView(APIView):
    """
    An endpoint to logout users by blacklisting their refresh token.
    """
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)

class UserSoftDeleteAPIView(generics.DestroyAPIView):
    """
    API view to soft-delete a user.
    Only allows DELETE requests.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    
    permission_classes = [permissions.IsAdminUser]

    def destroy(self, request, *args, **kwargs):
        """
        Overrides the default destroy method to return a custom message.
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        
        return Response(
            {"message": f"User '{instance.email}' was successfully soft-deleted."},
            status=status.HTTP_200_OK
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
    callback_url = "http://localhost:5173"  

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        
        user = self.user

        if user and user.is_authenticated:
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)
            email = user.email
            user_id = user.id

            return Response({
                'access': access_token,
                'refresh': refresh_token,
                'email': email,
                'user_id': user_id,
            })
        return response



class InviteUserView(generics.CreateAPIView):
    """
    API endpoint for an OWNER to invite a new user.
    POST /api/users/invite/
    """
    serializer_class = InvitationSerializer
    permission_classes = [IsOwnerOrAdmin] # Only allows OWNERS

    def perform_create(self, serializer):
        invitation = serializer.save(invited_by=self.request.user)
        temporary_password = get_random_string(length=12)
        User.objects.create_user(
            email=invitation.email,
            password=None,
            role=invitation.role,
            is_active=False # User remains inactive until password is set
        )

        invitation_link = f"http://localhost:5173/set-password?token={invitation.token}"
        send_mail(
            subject='You have been invited to join test-app!',
            message=f"Hello, Please click the link to set your password and activate your account: {invitation_link}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
        )
        # response_data = {
        #     'email': invitation.email,
        #     'role': invitation.role,
        #     'token': str(invitation.token) 
        # }

        # headers = self.get_success_headers(serializer.data)
        # return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)

class SetPasswordView(generics.GenericAPIView):
    """
    API endpoint for an invited user to set their password and activate their account.
    POST /api/users/set-password/
    """
    serializer_class = SetPasswordSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data['token']
        password = serializer.validated_data['password']

        try:
            invitation = Invitation.objects.get(token=token, status=Invitation.Status.PENDING)
            user = User.objects.get(email=invitation.email)

            user.set_password(password)
            user.is_active = True
            user.save()

            invitation.status = Invitation.Status.ACCEPTED
            invitation.save()

            return Response({"message": "Password set successfully. You can now log in."}, status=status.HTTP_200_OK)

        except (Invitation.DoesNotExist, User.DoesNotExist):
            return Response({"error": "Invalid token or user not found."}, status=status.HTTP_400_BAD_REQUEST)



class UserRoleUpdateView(generics.UpdateAPIView):
    """
    API endpoint for an OWNER to change another user's role.
    PUT/PATCH /api/users/{id}/change-role/
    """
    queryset = User.objects.all()
    serializer_class = UserRoleSerializer
    permission_classes = [IsOwnerUser,IsAuthenticated] # Only allows OWNERS

class UserRolesView(APIView):
    """
    An endpoint to get the list of available roles for inviting users.
    The list is filtered based on the role of the user making the request.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        all_roles = User.Role.choices
        user_role = getattr(request.user, 'role', None)

        if user_role == User.Role.ADMIN:
            invitable_roles = [role for role in all_roles if role[0] != User.Role.ADMIN]
            return Response(invitable_roles)

        if user_role == User.Role.OWNER:
            invitable_roles = [role for role in all_roles if role[0] not in [User.Role.ADMIN, User.Role.OWNER]]
            return Response(invitable_roles)

        if user_role == User.Role.MANAGER:
            invitable_roles = [role for role in all_roles if role[0] in [User.Role.DEVELOPER, User.Role.TESTER]]
            return Response(invitable_roles)

        return Response([])


