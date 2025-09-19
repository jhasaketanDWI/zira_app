from django.utils.decorators import method_decorator
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import action
from .models import( TestCase, 
                    Project,
                      User,
                        SubscriptionPlan, 
                        Subscription,
                          Invoice,
                            ProjectMember,
                              Epic, 
                              Sprint,
                                 Ticket
                                   )
from rest_framework import viewsets, permissions, generics,viewsets, status, exceptions
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from .permissions import IsOwnerOrAdmin
from .utils import get_client_ip


from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import(
     UserSerializer, 
     UserSignUpSerializer,
     AdminSignUpSerializer,
     TestCaseSerializer, 
     TestCaseStatusUpdateSerializer,
     ProjectSerializer,
     SubscriptionPlanSerializer,
     SubscriptionSerializer,
     InvoiceSerializer,
     ProjectSerializer, 
     ProjectMemberSerializer,
       EpicSerializer,
         SprintSerializer,
         TicketSerializer
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

# Add this new view to render your HTML page
def index(request):
    """
    A view to render the main single-page application (SPA) interface.
    """
    return render(request, 'index.html')


class TestCaseViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Test Cases.

    - Create: `POST /api/testcases/`
    - List by Project: `GET /api/projects/{project_pk}/testcases/`
    - Update Status: `PUT /api/testcases/{pk}/status/`
    """
    queryset = TestCase.objects.all().select_related('project').order_by('-created_at')
    serializer_class = TestCaseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        If the view is accessed via a nested route from a project,
        this method filters the test cases for that specific project.
        """
        if 'project_pk' in self.kwargs:
            return self.queryset.filter(project_id=self.kwargs['project_pk'])
        return self.queryset

    def perform_create(self, serializer):
        """
        Overrides the default create behavior to handle project assignment
        and automatically set the source to 'MANUAL'.
        """
        project_id = None
        # Case 1: Called from a nested URL like /api/projects/{project_pk}/testcases/
        if 'project_pk' in self.kwargs:
            project_id = self.kwargs['project_pk']
        # Case 2: Called from /api/testcases/, project must be in request body
        elif 'project' in self.request.data:
            project_id = self.request.data['project']
        else:
            raise exceptions.ValidationError("Project ID must be provided.")

        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            raise exceptions.NotFound(f"Project with ID {project_id} not found.")

        serializer.save(
            source=TestCase.Source.MANUAL,
            project=project
        )

    @action(detail=True, methods=['put'], url_path='status', serializer_class=TestCaseStatusUpdateSerializer)
    def update_status(self, request, pk=None):
        """
        Custom action to update the status of a test case.
        Allows marking a test case as EXECUTED, BLOCKED, etc.
        Example: PUT /api/testcases/123/status/ with body {"status": "EXECUTED"}
        """
        test_case = self.get_object()
        serializer = self.get_serializer(test_case, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Return the full, updated test case representation for confirmation
        response_serializer = TestCaseSerializer(test_case)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
    

class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows subscription plans to be viewed or edited.
    Only admin users can modify subscription plans.
    """
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    # Permissions are set to IsAdminUser, as typically only admins should manage plans.
    permission_classes = [permissions.IsAdminUser]

    def perform_create(self, serializer):
        ip = get_client_ip(self.request)
        # Corrected to use the 'created_by' and 'updated_by' fields from AuditBaseModel.
        serializer.save(created_by=ip, updated_by=ip)

    def perform_update(self, serializer):
        ip = get_client_ip(self.request)
        # Corrected to use the 'updated_by' field.
        serializer.save(updated_by=ip)


class SubscriptionViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to view and manage their own subscriptions.
    """
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        This is a critical security correction.
        It ensures that users can only view their own subscriptions and not anyone else's.
        """
        return Subscription.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        ip = get_client_ip(self.request)
        # The owner is automatically set to the currently logged-in user.
        serializer.save(
            owner=self.request.user,
            created_by=ip,
            updated_by=ip,
        )

    def perform_update(self, serializer):
        ip = get_client_ip(self.request)
        serializer.save(updated_by=ip)


class InvoiceViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to view invoices for their subscriptions.
    """
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        This is another critical security correction.
        It ensures users can only see invoices that belong to their subscriptions.
        """
        return Invoice.objects.filter(subscription__owner=self.request.user)

    def perform_create(self, serializer):
        ip = get_client_ip(self.request)
        serializer.save(created_by=ip, updated_by=ip)

    def perform_update(self, serializer):
        ip = get_client_ip(self.request)
        serializer.save(updated_by=ip)



def check_project_permission(user, project, allowed_roles=None):
    """Utility function to check if user has required role for a project."""
    if allowed_roles is None:
        allowed_roles = ["OWNER", "PROJECT_MANAGER"]

    membership = ProjectMember.objects.filter(user=user, project=project).first()
    if not membership or membership.role not in allowed_roles:
        raise PermissionDenied("You do not have permission to perform this action.")

class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by("-id")
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated] 

    def perform_create(self, serializer):
        project = serializer.save(owner=self.request.user)
        ProjectMember.objects.create(
            user=self.request.user,
            project=project,
            role=ProjectMember.Role.OWNER
        )

    def perform_update(self, serializer):
        project = self.get_object()
        check_project_permission(self.request.user, project) 
        serializer.save()

    def list(self, request, *args, **kwargs):
        user_projects = Project.objects.filter(projectmember__user=request.user).distinct().order_by("-id")
        
        grouped = {
            "planned": [],
            "ongoing": [],
            "delayed": [],
            "completed": [],
            "archived": []
        }

        for project in user_projects:
            data = self.get_serializer(project).data
            if project.status in grouped:
                grouped[project.status].append(data)

        return Response(grouped)


class ProjectMemberViewSet(viewsets.ModelViewSet):
    queryset = ProjectMember.objects.all().order_by("-id")
    serializer_class = ProjectMemberSerializer

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        check_project_permission(self.request.user, project)  #  OWNER/PM required
        serializer.save()

    def perform_update(self, serializer):
        project = serializer.instance.project
        check_project_permission(self.request.user, project)
        serializer.save()

    def perform_destroy(self, instance):
        check_project_permission(self.request.user, instance.project)
        instance.delete()


class EpicViewSet(viewsets.ModelViewSet):
    queryset = Epic.objects.all().order_by("-id")
    serializer_class = EpicSerializer

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        check_project_permission(self.request.user, project)  # Owner/PM only
        serializer.save()

    def perform_update(self, serializer):
        project = serializer.instance.project
        check_project_permission(self.request.user, project)
        serializer.save()



class SprintViewSet(viewsets.ModelViewSet):
    queryset = Sprint.objects.all().order_by("-id")
    serializer_class = SprintSerializer

    def perform_create(self, serializer):
        project = serializer.validated_data["project"]
        check_project_permission(self.request.user, project)  # Owner/PM only
        serializer.save()

    def perform_update(self, serializer):
        project = serializer.instance.project
        check_project_permission(self.request.user, project)
        serializer.save()

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Custom action to activate a sprint (only one active sprint per project)."""
        sprint = self.get_object()
        check_project_permission(request.user, sprint.project)

        # Deactivate other sprints in the same project
        Sprint.objects.filter(project=sprint.project).update(is_active=False)
        sprint.is_active = True
        sprint.save()

        return Response({"status": "Sprint activated successfully."}, status=status.HTTP_200_OK)
    
    @action(detail=True, methods=["put"])
    def end(self, request, pk=None):
        sprint = self.get_object()
        check_project_permission(request.user, sprint.project)

        if sprint.is_ended:
            return Response({"detail": "Sprint is already ended."}, status=status.HTTP_400_BAD_REQUEST)

        sprint.is_active = False
        sprint.is_ended = True
        sprint.save()

        return Response({"status": "Sprint ended successfully."}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def tickets(self, request, pk=None):
        sprint = self.get_object()
        check_project_permission(request.user, sprint.project)

        tickets = sprint.tickets.all()
        serializer = TicketSerializer(tickets, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class TicketViewSet(viewsets.ModelViewSet):
    queryset = Ticket.objects.all()
    serializer_class = TicketSerializer

    def perform_create(self, serializer):
        
        serializer.save()
