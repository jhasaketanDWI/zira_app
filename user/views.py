from django.utils.decorators import method_decorator
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from .models import User,Invitation
from rest_framework import viewsets, permissions, generics,viewsets, status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import MyTokenObtainPairSerializer
from rest_framework.views import APIView
from project.models import ProjectInvitation
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from django.core.mail import send_mail
from common.permissions import IsOwnerUser,IsOwnerAdminOrScrumMaster, IsOwnerOrAdmin,IsOwnerAdminOrManager,IsOwnerAdminOrScrumMasterOrManager,RBACPermission, IsSuperAdminOrDjangoAdmin
from django.utils.crypto import get_random_string
from django.db.models import Q
from .serializers import(
     UserSerializer, 
     UserSignUpSerializer,
     AdminSignUpSerializer,
     AdminUserManagementSerializer,
     InvitationSerializer, SetPasswordSerializer, UserRoleSerializer,
     RoleSerializer, PermissionSerializer, OwnerSignupWithOrganizationSerializer
     )
from project.models import Project, ProjectMember
from django.contrib.auth.models import Permission, Group
from django.shortcuts import get_object_or_404



# These imports are required to set up the Google social login endpoint
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework.decorators import action

# These imports are required to set up the Google social login endpoint
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView
from rest_framework.decorators import action
from common.utils.email_service import send_notification_email


class CurrentUserView(generics.RetrieveAPIView):
    """
    An endpoint to get the details of the currently authenticated user.
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated,RBACPermission] # Only logged-in users can access
    perms_map = {
        'list': 'user.can_view_all_users',
        'retrieve': 'user.can_view_all_users',
        'create': 'user.can_create_system_users',
        'update': 'user.can_edit_users_info',
        'partial_update': 'user.can_edit_users_info',
        'destroy': 'user.can_delete_users',
        
        # Custom actions
        'deactivate': 'user.can_edit_users_info', 
        'activate': 'user.can_edit_users_info',
        'reset_password': 'user.can_reset_passwords',
    }


    def get_object(self):
        """
        Returns the currently authenticated user.
        """
        return self.request.user
class UserViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for OWNERs and ADMINs to view, create, and edit all users.
    """
    queryset = User.objects.all().order_by('-id').filter(is_deleted=False)
    
    # permission_classes = [IsOwnerOrAdmin,IsAuthenticated]
    permission_classes = [IsAuthenticated, RBACPermission]
    perms_map = {
        'list': 'user.can_view_all_users',
        'retrieve': 'user.can_view_all_users',
        'create': 'user.can_create_system_users',
        'update': 'user.can_edit_users_info',
        'partial_update': 'user.can_edit_users_info',
        'destroy': 'user.can_delete_users',
        
        # Custom actions
        'deactivate': 'user.can_edit_users_info', 
        'activate': 'user.can_edit_users_info',
        'reset_password': 'user.can_reset_passwords',
    }

    def get_queryset(self):
        """
        Dynamically filter the queryset.
        - Exclude soft-deleted users.
        - If the user is an OWNER, exclude them from the list.
        """
        user = self.request.user
        base_queryset = User.objects.filter(is_deleted=False).order_by('-id')

        if not user.is_super_admin:
            base_queryset = base_queryset.filter(organization=user.organization)

        # Check if the user is authenticated and has the OWNER role
        if user.is_authenticated and user.role == User.Role.OWNER:
            # Exclude the owner from the list
            return base_queryset.exclude(id=user.id)
        
        # For Admins, return the full list
        return base_queryset
    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return AdminUserManagementSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        # [EMAIL] System User Created Manually
        send_notification_email(
            subject="Account Created",
            recipients=[user.email],
            template_path="emails/notification.html",
            context={
                'title': "Welcome to the System",
                'message_body': f"An account has been created for you by {request.user.get_full_name()}.",
                'details': {'Username': user.email, 'Role': user.role},
                'action_url': f"{settings.FRONTEND_URL}/login"
            }
        )
        response_serializer = UserSerializer(user)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'],url_path='deactivate-user')
    def deactivate(self, request, pk=None):
        user = self.get_object()
        user.is_active = False
        user.save()
         # [EMAIL] User Deactivated
        send_notification_email(
            subject="Account Deactivated",
            recipients=[user.email],
            template_path="emails/notification.html",
            context={
                'title': "Account Deactivated",
                'message_body': "Your account has been deactivated by an administrator. Please contact support if you believe this is an error.",
                'details': {'Action By': request.user.get_full_name()}
            }
        )
        return Response({'status': 'user deactivated'})

    @action(detail=True, methods=['patch'],url_path='activate-user')
    def activate(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save()
        # [EMAIL] User Reactivated
        send_notification_email(
            subject="Account Reactivated",
            recipients=[user.email],
            template_path="emails/notification.html",
            context={
                'title': "Account Active",
                'message_body': "Your account has been reactivated. You may now log in.",
                'action_url': f"{settings.FRONTEND_URL}/login"
            }
        )
        return Response({'status': 'user activated'})


class OwnerSignupWithOrganizationView(APIView):
    """
    Public endpoint for first-time users to sign up and create an organization.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OwnerSignupWithOrganizationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED
        )


class AdminUserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    permission_classes = [IsAuthenticated,RBACPermission]
    perms_map = {
        'list': 'user.can_view_all_users',
        'retrieve': 'user.can_view_all_users',
        'create': 'user.can_create_system_users',
        'update': 'user.can_edit_users_info',
        'partial_update': 'user.can_edit_users_info',
        'destroy': 'user.can_delete_users',
        
        # Custom actions
        'deactivate': 'user.can_edit_users_info', 
        'activate': 'user.can_edit_users_info',
        'reset_password': 'user.can_reset_passwords',
    }

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
    permission_classes = [IsAuthenticated, IsOwnerAdminOrScrumMasterOrManager]
    def get(self, request, *args, **kwargs):
        user = request.user
        if user.role == User.Role.OWNER or user.role == User.Role.ADMIN or user.role == User.Role.SCRUM_MASTER:
            # --- Global Stats for Owner/Admin ---
            if user.is_super_admin:
                total_members = User.objects.filter(is_deleted=False).count()
                active_members = User.objects.filter(is_active=True, is_deleted=False).count()
                active_projects = Project.objects.exclude(
                    status__in=[Project.Status.COMPLETED, Project.Status.ARCHIVED]
                ).count()
            else:
                total_members = User.objects.filter(
                    organization=user.organization,
                    is_deleted=False
                ).count()

                active_members = User.objects.filter(
                    organization=user.organization,
                    is_active=True,
                    is_deleted=False
                ).count()

                active_projects = Project.objects.filter(
                    organization=user.organization
                ).exclude(
                    status__in=[Project.Status.COMPLETED, Project.Status.ARCHIVED]
                ).count()

            stats = {
                'total_members': total_members,
                'active_members': active_members,
                'active_projects': active_projects
            }
            return Response(stats)

        elif user.role == User.Role.MANAGER:
            try:
                managed_project_ids = ProjectMember.objects.filter(
                    user=user, 
                    role="MANAGER",
                    organization=user.organization,
                ).values_list('project_id', flat=True)

                if not managed_project_ids:
                    return Response({
                        # 'scope': 'managed_projects',
                        'total_members': 0,
                        'active_members': 0,
                        'active_projects': 0,
                        'message': 'This manager is not assigned to any projects.'
                    })

                managed_projects = Project.objects.filter(organization=user.organization, id__in=managed_project_ids)

                active_projects = managed_projects.exclude(
                    status__in=[Project.Status.COMPLETED, Project.Status.ARCHIVED]
                ).count()
                
                project_manager_user_ids = ProjectMember.objects.filter(
                    project_id__in=managed_project_ids,
                    role="MANAGER"
                ).values_list('user_id', flat=True).distinct()

                # 5. Get all users who are members of those projects...
                team_members = User.objects.filter(
                    organization=user.organization,
                    projectmember__project_id__in=managed_project_ids
                ).exclude(
                    # ...but are NOT global Admins or Owners
                    Q(role=User.Role.ADMIN) | Q(role=User.Role.OWNER)
                ).exclude(
                    # ...and are NOT in the list of Project Managers
                    id__in=project_manager_user_ids
                ).distinct()
                
                total_members = team_members.count()
                active_members = team_members.filter(is_active=True).count()

                stats = {
                    # 'scope': 'managed_projects',
                    'total_members': total_members,       # Total unique users in their projects
                    'active_members': active_members,      # Active users from that group
                    'active_projects': active_projects     # Active projects they manage
                }
                return Response(stats)

            except NameError:
                return Response(
                    {'error': 'The `ProjectMember` model could not be imported. Check the import in `users/views.py`.'}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            except Exception as e:
                # This will catch errors if field names (user, project, role) are wrong
                return Response(
                    {'error': f'An error occurred. Check ProjectMember model relations. Details: {e}'}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response(
            {'detail': 'You do not have permission to perform this action.'}, 
            status=status.HTTP_403_FORBIDDEN
        )



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
    
    permission_classes = [IsSuperAdminOrDjangoAdmin]

    def destroy(self, request, *args, **kwargs):
        """
        Overrides the default destroy method to return a custom message.
        """
        instance = self.get_object()
        user_name = instance.get_full_name()
        user_email = instance.email

        self.perform_destroy(instance)
         # --- [EMAIL INTEGRATION] User Removed Broadcast ---
        # "if a user is deleted then send mail to other users that he/she has been removed"
        
        # Get all active users to notify
        recipients = User.objects.filter(is_active=True, is_deleted=False).exclude(id=instance.id).values_list('email', flat=True)
        
        send_notification_email(
            subject=f"[User Removed] {user_name} has left the organization",
            recipients=list(recipients),
            template_path="emails/notification.html",
            context={
                'title': "User Removed",
                'message_body': f"The user {user_name} ({user_email}) has been removed from the system.",
                'details': {
                    'Removed User': user_name,
                    'Removed By': request.user.get_full_name()
                }
            }
        )
        
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
    # callaback_url = "https://kanban.dreamwaveinnovations.com"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        
        user = self.user

        if user and user.is_authenticated:
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)
            refresh_token = str(refresh)
            email = user.email
            user_id = user.id
            role=user.role

            return Response({
                'access': access_token,
                'refresh': refresh_token,
                'email': email,
                'role':role,
                'user_id': user_id,
            })
        return response



class InviteUserView(generics.CreateAPIView):
    """
    API endpoint for an OWNER to invite a new user.
    POST /api/users/invite/
    """
    serializer_class = InvitationSerializer
    permission_classes = [IsAuthenticated, IsOwnerOrAdmin, RBACPermission   ]
    perms_map = {
        'create': 'user.can_invite_users',

    }

    def perform_create(self, serializer):
        invitation = serializer.save(
            invited_by=self.request.user,
            organization=self.request.user.organization
        )
        temporary_password = get_random_string(length=12)
        User.objects.create_user(
            email=invitation.email,
            password=None,
            role=invitation.role,
            is_active=False,
            organization=self.request.user.organization
        )

        # invitation_link = f"https://kanban.dreamwaveinnovations.com/set-password?token={invitation.token}"
        # send_mail(
        #     subject='You have been invited to join test-app!',
        #     message=f"Hello, Please click the link to set your password and activate your account: {invitation_link}",
        #     from_email=settings.DEFAULT_FROM_EMAIL,
        #     recipient_list=[invitation.email],
        # )

         # --- [EMAIL INTEGRATION] Invitation Email ---
        invitation_link = f"{settings.FRONTEND_URL}/set-password?token={invitation.token}"
        
        send_notification_email(
            subject='You have been invited to join the Team',
            recipients=[invitation.email],
            template_path="emails/notification.html",
            context={
                'title': "Welcome!",
                'message_body': f"Hello, you have been invited to join the platform by {self.request.user.get_full_name()}.",
                'details': {
                    'Role': invitation.role,
                    'Invited By': self.request.user.get_full_name()
                },
                'action_url': invitation_link
            }
        )

class SetPasswordView(APIView):
    """
    A "smart" view that activates a user's account and sets their password.
    It can handle tokens from EITHER a system-level invitation (user.Invitation)
    OR a project-level invitation (project.ProjectInvitation).
    """
    permission_classes = [AllowAny]
    serializer_class = SetPasswordSerializer # Use your existing serializer for validation

    def post(self, request, *args, **kwargs):
        token_str = request.data.get('token')
        if not token_str:
            return Response({'error': 'Token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # We need to find the user, but they could be from one of two tables.
        user_to_activate = None
        invitation_to_accept = None
        is_project_invite = False

        # --- Try 1: Check for a Project Invitation token ---
        try:
            project_invite = ProjectInvitation.objects.get(token=token_str, status=ProjectInvitation.Status.PENDING)
            user_to_activate = project_invite.user_to_invite
            invitation_to_accept = project_invite
            is_project_invite = True
        except ProjectInvitation.DoesNotExist:
            pass # Not a project invite, so we check the system invites next

        # --- Try 2: Check for a System Invitation token (your old logic) ---
        if not user_to_activate:
            try:
                system_invite = Invitation.objects.get(token=token_str, status=Invitation.Status.PENDING)
                # Find the inactive user by email
                user_to_activate = User.objects.get(email__iexact=system_invite.email, is_active=False)
                invitation_to_accept = system_invite
            except (Invitation.DoesNotExist, User.DoesNotExist):
                # Token is not in EITHER table
                return Response({'error': 'Invalid or expired invitation token.'}, status=status.HTTP_404_NOT_FOUND)

        # At this point, we have a valid `user_to_activate` and `invitation_to_accept`
        
        # Use your serializer to validate the password
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        password = serializer.validated_data['password']

        # Activate the user and set the password
        user_to_activate.set_password(password)
        user_to_activate.is_active = True
        user_to_activate.save()

        # Mark the invitation as accepted
        invitation_to_accept.status = "ACCEPTED" # Both models use "ACCEPTED"
        invitation_to_accept.save()

        # --- [EMAIL INTEGRATION] Broadcast New User Joined ---
        # "send mail to all other users... if multiple user joined... send one by one"
        # The email service handles the loop.

        all_active_users = User.objects.filter(
            is_active=True,
            is_deleted=False
        ).filter(
            organization=user_to_activate.organization
        ) | User.objects.filter(is_super_admin=True)
        
        send_notification_email(
            subject=f"[New Member] {user_to_activate.get_full_name()} has joined!",
            recipients=list(all_active_users),
            template_path="emails/notification.html",
            context={
                'title': "New Team Member",
                'message_body': f"Please welcome {user_to_activate.get_full_name()} to the organization.",
                'details': {
                    'Name': user_to_activate.get_full_name(),
                    'Email': user_to_activate.email,
                    'Role': user_to_activate.role
                }
            }
        )


        return Response({'status': 'Account activated and password set successfully.'}, status=status.HTTP_200_OK)
class ManagerTeamListView(generics.ListAPIView):
    """
    API endpoint for a Project Manager to see their team members.
    
    Returns a list of all users who are in the same projects
    as the requesting user (where the user is a 'PROJECT_MANAGER').
    
    Excludes:
    - Global Admins (User.role == "ADMIN")
    - Global Owners (User.role == "OWNER")
    - Other Project Managers (ProjectMember.role == "PROJECT_MANAGER")
    - The user themselves
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated] # Only authenticated users can access

    def get_queryset(self):
        user = self.request.user

        try:
            managed_project_ids = ProjectMember.objects.filter(
                user=user, 
                role="MANAGER" # Using the project-specific role
            ).values_list('project_id', flat=True)

            if not managed_project_ids.exists():
                return User.objects.none()

            
            project_manager_user_ids = ProjectMember.objects.filter(
                project_id__in=managed_project_ids,
                role="MANAGER"
            ).values_list('user_id', flat=True).distinct()

            queryset = User.objects.filter(
                projectmember__project_id__in=managed_project_ids
            ).exclude(
                Q(role=User.Role.ADMIN) | Q(role=User.Role.OWNER)
            ).exclude(
                id__in=project_manager_user_ids
            ).distinct().order_by('email')
            
            return queryset
            
        except (NameError, AttributeError):
            return User.objects.none()
        except Exception as e:
            print(f"Error in ManagerTeamListView: {e}") # For your debugging
            return User.objects.none()


class UserRoleUpdateView(generics.UpdateAPIView):
    """
    API endpoint for an OWNER to change another user's role.
    PUT/PATCH /api/users/{id}/change-role/
    """
    queryset = User.objects.all()
    serializer_class = UserRoleSerializer
    permission_classes = [IsOwnerUser,IsAuthenticated,RBACPermission] # Only allows OWNERS
    perms_map = {
        'update': 'user.can_edit_users_info', 
        'partial_update': 'user.can_edit_users_info'
    }
class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API: GET /api/rbac/permissions/
    Lists all system permissions. The frontend uses this to populate the checkboxes.
    """
    serializer_class = PermissionSerializer
    permission_classes = [IsOwnerOrAdmin,IsAuthenticated]
    def get_queryset(self):
        MY_APPS = [
            'project', 
            'task', 
            'user', 
            'team',      
            'billing', 
            'pages',      
            'testCase', 
        ]

        queryset = Permission.objects.filter(content_type__app_label__in=MY_APPS)

        # 2. (Optional) Hide the default Django add/change/delete permissions
        #    If you want to rely ONLY on your custom "can_create_project" and 
        #    hide the auto-generated "add_project", uncomment these lines:
        
        queryset = queryset.exclude(codename__startswith='add_') \
                           .exclude(codename__startswith='change_') \
                           .exclude(codename__startswith='delete_') \
                           .exclude(codename__startswith='view_')

        return queryset.order_by('id')
    # # Exclude internal Django permissions to keep the list clean
    # queryset = Permission.objects.exclude(
    #     content_type__app_label__in=['admin', 'contenttypes', 'sessions', 'authtoken']
    # ).distinct().order_by('id')
    # # ).order_by('content_type__app_label', 'codename')
    

class RoleViewSet(viewsets.ModelViewSet):
    """
    Unified Endpoint for Role Management.
    
    1. Standard CRUD (Admin Only):
       - GET /api/rbac/roles/       -> List all roles
       - POST /api/rbac/roles/      -> Create new role
       - PUT /api/rbac/roles/{id}/  -> Update role permissions
       
    2. Invitable Roles (Authenticated Users):
       - GET /api/rbac/roles/invitable/ -> List roles the user is allowed to invite
    """
    queryset = Group.objects.all().order_by('name')
    serializer_class = RoleSerializer
    
    # default permission for standard CRUD is Admin Only
    # permission_classes = [IsAuthenticated]

    # def get_permissions(self):
    #     """
    #     Custom permissions:
    #     - The 'invitable' action is accessible to any logged-in user (IsAuthenticated).
    #     - Everything else (Create, Delete, List All) is restricted to Admins (IsSuperAdminOrDjangoAdmin).
    #     """
    #     if self.action == 'invitable':
    #         return [IsAuthenticated()]
    #     return [IsSuperAdminOrDjangoAdmin() or IsOwnerOrAdmin()]
    
    @action(detail=False, methods=['get'], url_path='by-name')
    def get_by_name(self, request):
        """
        GET /api/rbac/roles/by-name/?name=Manager
        Fetches a specific role and its permissions using the role name.
        """
        role_name = request.query_params.get('name')
        
        if not role_name:
            return Response(
                {"error": "The 'name' query parameter is required."}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Case-sensitive exact match. Use name__iexact for case-insensitive.
        role = get_object_or_404(Group, name=role_name)
        
        # This uses your existing RoleSerializer, which already includes permissions
        serializer = self.get_serializer(role)
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='available-roles')
    def invitable(self, request):
        """
        Replaces the old UserRolesView.
        Returns a filtered list of roles based on the requester's hierarchy.
        """
        user_role = getattr(request.user, 'role', None)

        # Define the hierarchy logic
        HIERARCHY = {
            'OWNER': ['ADMIN', 'MANAGER', 'SCRUM_MASTER', 'DEVELOPER', 'TESTER', 'VIEWER'],
            'ADMIN': ['MANAGER', 'SCRUM_MASTER', 'DEVELOPER', 'TESTER', 'VIEWER'],
            'SCRUM_MASTER': ['MANAGER', 'DEVELOPER', 'TESTER', 'VIEWER'],
            'MANAGER': ['DEVELOPER', 'TESTER', 'VIEWER'],
            # Developers/Testers typically cannot invite anyone
            'DEVELOPER': [],
            'TESTER': [],
        }

        # Get allowed role names
        allowed_names = HIERARCHY.get(user_role, [])
        
        # Fetch actual Group objects
        groups = Group.objects.filter(name__in=allowed_names).order_by('name')
        
        # Use the serializer to return standard data structure
        # (Pass 'many=True' because we are serializing a list of groups)
        serializer = self.get_serializer(groups, many=True)
        
        return Response(serializer.data)


class FilteredUserListView(generics.ListAPIView):
    """
    Provides a list of users based on the role of the requesting user
    and an optional 'role' query parameter.
    
    Example Usage:
    - GET /api/users/list/ -> Returns all users the requester is allowed to see.
    - GET /api/users/list/?role=developer -> Returns only developers the requester is allowed to see.
    """
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        requesting_user = self.request.user
        
        # Determine the roles the current user is allowed to see based on hierarchy
        if requesting_user.role == User.Role.OWNER:
            allowed_roles = [User.Role.MANAGER,User.Role.SCRUM_MASTER, User.Role.DEVELOPER, User.Role.TESTER]
        elif requesting_user.role == User.Role.ADMIN:
            # Assuming Admin is the highest level and can see all other roles
            allowed_roles = [User.Role.OWNER, User.Role.MANAGER,User.Role.SCRUM_MASTER, User.Role.DEVELOPER, User.Role.TESTER]
        elif requesting_user.role == User.Role.MANAGER:
            allowed_roles = [User.Role.DEVELOPER, User.Role.TESTER]
        elif requesting_user.role == User.Role.SCRUM_MASTER:
            allowed_roles = [User.Role.DEVELOPER, User.Role.TESTER, User.Role.MANAGER]
        else: # Developers and Testers have no subordinates to view
            allowed_roles = []
        
        # Start with the base queryset of users in the allowed roles
        if requesting_user.is_super_admin:
            queryset = User.objects.filter(
                is_deleted=False,
                is_active=True,
                role__in=allowed_roles,
            )
        else:
            queryset = User.objects.filter(
                is_deleted=False,
                is_active=True,
                role__in=allowed_roles,
                organization=requesting_user.organization
            )

        # Apply the optional role filter from the query parameter
        role_filter = self.request.query_params.get('role', None)
        if role_filter:
            # This filter is securely applied to the already-restricted queryset
            queryset = queryset.filter(role__iexact=role_filter)
        
        return queryset.order_by('email')