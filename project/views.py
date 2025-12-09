from django.core.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from django.db.models import Q
from .models import( Project,ProjectMember, ProjectInvitation)
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, AllowAny
from .serializers import(ProjectSerializer, ProjectMemberSerializer, ProjectDetailSerializer,ActivityLogSerializer,_UserNestedSerializer, ProjectMemberBulkAssignByRoleSerializer, ProjectMemberInviteSerializer)
from rest_framework.views import APIView
from task.models import Task, ActivityLog
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count
from user.models import User, Invitation
from django.core.mail import send_mail
from django.conf import settings
from common.permissions import IsOwnerAdminOrManager
from user.serializers import UserSerializer
from django.db import transaction
class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by("-id")
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated] 

    def get_serializer_class(self):
        if self.action == 'retrieve':
                return ProjectDetailSerializer
        return ProjectSerializer
    def get_queryset(self):
        user=self.request.user
        return Project.objects.filter(
            Q(owner=user) | Q(projectmember__user=user)
        ).distinct() .order_by("-id")
    @transaction.atomic
    def perform_create(self, serializer):
        manager_to_assign = serializer.validated_data.get('MANAGER ')

        # 1. Save the Project (Creator becomes the Project Owner)
        project = serializer.save(owner=self.request.user)
        creator = self.request.user

        # FIX 1: Use a set of IDs for efficient lookups and exclusion
        # Initialize with the creator's ID
        users_to_exclude_ids = {creator.id}
        
        # FIX 2: Create a list of ProjectMember objects directly
        members_to_create = []
        
        # Add the creator (owner) immediately
        members_to_create.append(
            ProjectMember(
                user=creator,
                project=project,
                role=ProjectMember.Role.OWNER
            )
        )
        
        # --- NEW LOGIC: Automatically Add Organization Owner and Scrum Masters ---
        
        # 2. Find the Organization Owner(s)
        # Assuming the role is 'ORG_OWNER'
        org_owners = User.objects.filter(role='OWNER').exclude(id__in=users_to_exclude_ids)
        for owner in org_owners:
            members_to_create.append(
                ProjectMember(
                    user=owner,
                    project=project,
                    role=ProjectMember.Role.OWNER # Assign the highest role for visibility
                )
            )
            users_to_exclude_ids.add(owner.id) # Track ID to exclude from later queries

        # 3. Find all Scrum Masters
        scrum_masters = User.objects.filter(role='SCRUM_MASTER').exclude(id__in=users_to_exclude_ids)
        for sm in scrum_masters:
            # Add them with the Scrum Master role
            members_to_create.append(
                ProjectMember(
                    user=sm,
                    project=project,
                    role=ProjectMember.Role.SCRUM_MASTER
                )
            )
            users_to_exclude_ids.add(sm.id)
            
        # 4. Handle Manager assignment (if provided in the request)
        if manager_to_assign and manager_to_assign != creator:
            # Check if manager is already added as Owner/SCM
            if manager_to_assign.id not in users_to_exclude_ids:
                members_to_create.append(
                    ProjectMember(
                        user=manager_to_assign,
                        project=project,
                        role=ProjectMember.Role.MANAGER
                    )
                )
            
        # 5. Create all ProjectMember entries in bulk
        ProjectMember.objects.bulk_create(members_to_create)

    def perform_update(self, serializer):
        project = self.get_object()
        try:
            member = ProjectMember.objects.get(project=project, user=self.request.user)
            if member.role not in [ProjectMember.Role.OWNER, ProjectMember.Role.MANAGER ]:
                raise PermissionDenied("You do not have permission to edit project details.")
        except ProjectMember.DoesNotExist:
            raise PermissionDenied("You are not a member of this project.")
        serializer.save()

    def list(self, request, *args, **kwargs):
        user_projects = Project.objects.filter(
            projectmember__user=request.user
        ).distinct().order_by("-id")

        grouped = {
            "planned": [],
            "ongoing": [],
            "delayed": [],
            "completed": [],
            "archived": []
        }

        for project in user_projects:
            data = self.get_serializer(project).data
            status_key = project.status.lower()
            if status_key in grouped:
                grouped[status_key].append(data)

        return Response(grouped)


    @action(detail=True, methods=['get'], url_path='available-members/(?P<role>[a-zA-Z]+)')
    def available_members(self, request, role, pk=None):
        """
        This is Requirement #2 & #5 (part 1): Find available users with a specific global role.
        """
        project = self.get_object()
        try:
            requester_membership = ProjectMember.objects.get(project=project, user=request.user)
            requester_role = requester_membership.role
        except ProjectMember.DoesNotExist:
            return Response({"error": "You are not a member of this project."}, status=status.HTTP_403_FORBIDDEN)
        
        allowed_roles_to_query = []
        if requester_role == ProjectMember.Role.OWNER:
            allowed_roles_to_query = ['manager', 'developer', 'tester','scrum_master']
        elif requester_role == ProjectMember.Role.MANAGER :
            allowed_roles_to_query = ['developer', 'tester']
        elif requester_role == ProjectMember.Role.SCRUM_MASTER :
            allowed_roles_to_query = ['developer', 'tester', 'manager']

        if role.lower() not in allowed_roles_to_query:
            return Response({"error": f"As a {requester_role}, you cannot query for available {role}s."}, status=status.HTTP_403_FORBIDDEN)

        existing_member_ids = ProjectMember.objects.filter(project=project).values_list('user_id', flat=True)
        available_users = User.objects.exclude(id__in=existing_member_ids)
        
        global_role_map = {'manager': 'MANAGER', 'developer': 'DEVELOPER', 'tester': 'TESTER', 'scrum_master': 'SCRUM_MASTER' }
        role_to_filter_by = global_role_map.get(role.lower())
        if role_to_filter_by:
            available_users = available_users.filter(role=role_to_filter_by)

        serializer = _UserNestedSerializer(available_users, many=True)
        return Response(serializer.data)


class ProjectMemberViewSet(viewsets.ModelViewSet):
    """
    MODIFIED: This viewset is now nested under /projects/{project_pk}/members/
    """
    serializer_class = ProjectMemberSerializer
    permission_classes = [IsAuthenticated,IsOwnerAdminOrManager ]

    def get_queryset(self):
        """
        This viewset now only returns members for the project specified
        in the URL, AND filters the list based on the requester's role.
        """
        project_pk = self.kwargs.get('project_pk')
        user = self.request.user

        if not project_pk:
            return ProjectMember.objects.none()

        try:
            requester_membership = ProjectMember.objects.get(project_id=project_pk, user=user)
            requester_role = requester_membership.role
        except ProjectMember.DoesNotExist:
            return ProjectMember.objects.none()

        base_queryset = ProjectMember.objects.filter(project_id=project_pk)

        # 3. Apply filtering based on the user's role
        
        # If the user is a MANAGER, only show Developers and Testers
        if requester_role == ProjectMember.Role.MANAGER:
            return base_queryset.filter(
                role__in=[ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]
            ).order_by('-id')
        
        # For all other roles (OWNER, DEVELOPER, TESTER),
        # show everyone except themselves.
        return base_queryset.exclude(user=user).order_by('-id')

    def perform_create(self, serializer):
        project_pk = self.kwargs.get('project_pk')
        try:
            project = Project.objects.get(pk=project_pk)
        except Project.DoesNotExist:
            raise PermissionDenied("Project not found.")

        role_to_assign = serializer.validated_data["role"]

        # if role_to_assign == ProjectMember.Role.MANAGER :
        #     if ProjectMember.objects.filter(project=project, role=ProjectMember.Role.MANAGER ).exists():
        #         raise PermissionDenied("A Project Manager already exists for this project.")
        
        requester_role = self._get_requester_role(self.request.user, project)

        if requester_role == ProjectMember.Role.OWNER:
            if role_to_assign == ProjectMember.Role.OWNER:
                raise PermissionDenied("Cannot assign another Owner.")
        elif requester_role == ProjectMember.Role.MANAGER :
            if role_to_assign not in [ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
                raise PermissionDenied("Project Managers can only assign Developers or Testers.")
        else:
            raise PermissionDenied("You do not have permission to add members to this project.")

        serializer.save(project=project)
    
    @action(detail=False, methods=['post'], url_path='bulk-assign/(?P<role>[a-zA-Z_]+)')
    def bulk_assign(self, request, role, project_pk=None):
        try:
            project = Project.objects.get(pk=project_pk)
        except Project.DoesNotExist:
            return Response({"error": "Project not found."}, status=status.HTTP_404_NOT_FOUND)

        # Convert the role from the URL to uppercase for consistent validation
        role_to_assign = role.upper()

        # Validate the role against the available choices
        if role_to_assign not in ProjectMember.Role.values:
            return Response({"error": f"'{role}' is not a valid role."}, status=status.HTTP_400_BAD_REQUEST)
        
        requester_role = self._get_requester_role(self.request.user, project)
        if not requester_role:
             return Response({"error": "You do not have permission to perform this action."}, status=status.HTTP_403_FORBIDDEN)

        # Permission Check
        can_assign = False
        if requester_role == ProjectMember.Role.OWNER and role_to_assign != ProjectMember.Role.OWNER:
            can_assign = True
        elif requester_role == ProjectMember.Role.MANAGER and role_to_assign in [ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
            can_assign = True
        
        if not can_assign:
            return Response({'error': f"As a {requester_role}, you cannot assign the role {role_to_assign}."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ProjectMemberBulkAssignByRoleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        user_ids = serializer.validated_data['user_ids']
        success_responses = []
        error_responses = []

        for user_id in user_ids:
            if ProjectMember.objects.filter(project=project, user_id=user_id).exists():
                error_responses.append({'user_id': user_id, 'error': "This user is already a member of the project."})
                continue

            try:
                user = User.objects.get(pk=user_id)
                member = ProjectMember.objects.create(project=project, user=user, role=role_to_assign)
                success_responses.append(ProjectMemberSerializer(member).data)
            except User.DoesNotExist:
                error_responses.append({'user_id': user_id, 'error': "User not found."})

        return Response({
            "assigned_members": success_responses,
            "failed_assignments": error_responses
        }, status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['post'], url_path='invite-member')
    def invite_member(self, request, project_pk=None):
        """
        Handles inviting a user (either new or existing) to a project.
        - If new, creates an inactive user and sends a set-password link.
        - If existing, sends an accept-invitation link.
        """
        try:
            project = Project.objects.get(pk=project_pk)
        except Project.DoesNotExist:
            return Response({"error": "Project not found."}, status=status.HTTP_404_NOT_FOUND)

        requester_role = self._get_requester_role(self.request.user, project)
        if not requester_role:
             return Response({"error": "You must be a member of this project to invite others."}, status=status.HTTP_403_FORBIDDEN)

        serializer = ProjectMemberInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email_to_invite = serializer.validated_data['email']
        project_role_to_assign = serializer.validated_data['role']

        # 1. Permission Check
        can_invite = False
        if requester_role == ProjectMember.Role.OWNER and project_role_to_assign in [ProjectMember.Role.MANAGER,ProjectMember.Role.SCRUM_MASTER, ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
            can_invite = True
        elif requester_role == ProjectMember.Role.MANAGER and project_role_to_assign in [ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
            can_invite = True
        
        if not can_invite:
            return Response({'error': f"As a {requester_role}, you do not have permission to invite a user with the role {project_role_to_assign}."}, status=status.HTTP_403_FORBIDDEN)
        
        # 2. Check if already a member or already has a pending invite
        if ProjectMember.objects.filter(project=project, user__email__iexact=email_to_invite).exists():
            return Response({'error': 'This user is already a member of this project.'}, status=status.HTTP_400_BAD_REQUEST)

        if ProjectInvitation.objects.filter(project=project, email__iexact=email_to_invite, status=ProjectInvitation.Status.PENDING).exists():
            return Response({'error': 'An invitation has already been sent to this email address for this project.'}, status=status.HTTP_400_BAD_REQUEST)

        # 3. --- HYBRID LOGIC ---
        existing_user = User.objects.filter(email__iexact=email_to_invite).first()

        if existing_user:
            # --- CASE 1: USER ALREADY EXISTS ---
            # Your new feature logic
            invitation = ProjectInvitation.objects.create(
                project=project,
                email=email_to_invite,
                role=project_role_to_assign,
                invited_by=request.user,
                user_to_invite=existing_user
            )
            
            accept_link = f"https://kanban.dreamwaveinnovations.com/accept-project-invite?token={invitation.token}"
            subject = f"You are invited to join Project: {project.name}"
            message = (
                f"Hello {existing_user.first_name or existing_user.email},\n\n"
                f"You've been invited to join the project '{project.name}' as a {project_role_to_assign}.\n"
                f"Please click the link to accept: {accept_link}"
            )
            
            send_mail(subject=subject, message=message, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[email_to_invite])
            
            return Response({
                'status': 'Invitation sent successfully. The user is already registered and needs to accept.'
            }, status=status.HTTP_201_CREATED)
        else:
            # --- CASE 2: USER IS NEW ---
            # Your old logic, modified to use the new invitation model
            
            # 1. Map ProjectRole to global UserRole
            global_role_map = {
                ProjectMember.Role.MANAGER: User.Role.MANAGER,
                ProjectMember.Role.DEVELOPER: User.Role.DEVELOPER,
                ProjectMember.Role.TESTER: User.Role.TESTER,
            }
            global_role = global_role_map.get(project_role_to_assign, User.Role.DEVELOPER)

            # 2. Create the inactive user (as you wanted)
            new_user = User.objects.create_user(
                email=email_to_invite, 
                password=None, 
                role=global_role, 
                is_active=False # User is inactive
            )
            
            # 3. Add them to the project (as you wanted)
            ProjectMember.objects.create(project=project, user=new_user, role=project_role_to_assign)

            # 4. Create the new invitation record to track the token
            invitation = ProjectInvitation.objects.create(
                project=project,
                email=email_to_invite,
                role=project_role_to_assign,
                invited_by=request.user,
                user_to_invite=new_user,
                status=ProjectInvitation.Status.PENDING # Mark as pending
            )
            
            # 5. Send the set password link
            # Point this to your ORIGINAL set-password frontend page
            set_password_link = f"https://kanban.dreamwaveinnovations.com/set-password?token={invitation.token}"
            
            subject = f"You are invited to join Project: {project.name}"
            message = (
                f"Hello,\n\n"
                f"You've been invited to join the project '{project.name}'.\n"
                f"Please click the link to set your password and activate your account: {set_password_link}"
            )
            
            send_mail(subject=subject, message=message, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[email_to_invite])

            return Response({
                'status': 'Invitation sent. A new inactive user has been created and added to the project.'
            }, status=status.HTTP_201_CREATED)

        # else:
        #     # --- CASE 2: USER IS NEW ---
        #     # Your old logic, but modified to use the new invitation model
            
        #     # Map ProjectRole to global UserRole
        #     global_role_map = {
        #         ProjectMember.Role.MANAGER: User.Role.MANAGER,
        #         ProjectMember.Role.SCRUM_MASTER : User.Role.SCRUM_MASTER,

        #         ProjectMember.Role.DEVELOPER: User.Role.DEVELOPER,
        #         ProjectMember.Role.TESTER: User.Role.TESTER,
        #     }
        #     global_role = global_role_map.get(project_role_to_assign, User.Role.DEVELOPER)

        #     # 1. Create the inactive user (as you wanted)
        #     new_user = User.objects.create_user(
        #         email=email_to_invite, 
        #         password=None, 
        #         role=global_role, 
        #         is_active=False # User is inactive
        #     )
            
        #     # 2. Add them to the project (as you wanted)
        #     ProjectMember.objects.create(project=project, user=new_user, role=project_role_to_assign)

        #     # 3. Create the new invitation record to track the token
        #     invitation = ProjectInvitation.objects.create(
        #         project=project,
        #         email=email_to_invite,
        #         role=project_role_to_assign,
        #         invited_by=request.user,
        #         user_to_invite=new_user,
        #         status=ProjectInvitation.Status.PENDING # Mark as pending
        #     )
            
        #     # 4. Send the set password link
        #     set_password_link = f"http://localhost:5173/activate-and-set-password?token={invitation.token}"
        #     subject = f"You are invited to join Project: {project.name}"
        #     message = (
        #         f"Hello,\n\n"
        #         f"You've been invited to join the project '{project.name}'.\n"
        #         f"Please click the link to set your password and activate your account: {set_password_link}"
        #     )
            
        #     send_mail(subject=subject, message=message, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[email_to_invite])

        #     return Response({
        #         'status': 'Invitation sent. A new inactive user has been created and added to the project.'
        #     }, status=status.HTTP_201_CREATED)
    # @action(detail=False, methods=['post'], url_path='invite-member')
    # def invite_member(self, request, project_pk=None):
    #     """
    #     Handles inviting a NEW user and simultaneously adding them to this project.
    #     Permissions are checked based on the inviter's role within the project.
    #     """
    #     try:
    #         project = Project.objects.get(pk=project_pk)
    #     except Project.DoesNotExist:
    #         return Response({"error": "Project not found."}, status=status.HTTP_404_NOT_FOUND)

    #     requester_role = self._get_requester_role(self.request.user, project)
    #     if not requester_role:
    #          return Response({"error": "You must be a member of this project to invite others."}, status=status.HTTP_403_FORBIDDEN)

    #     serializer = ProjectMemberInviteSerializer(data=request.data)
    #     serializer.is_valid(raise_exception=True)
    #     email_to_invite = serializer.validated_data['email']
    #     project_role_to_assign = serializer.validated_data['role']

    #     # Permission Check
    #     can_invite = False
    #     if requester_role == ProjectMember.Role.OWNER and project_role_to_assign in [ProjectMember.Role.MANAGER , ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
    #         can_invite = True
    #     elif requester_role == ProjectMember.Role.MANAGER and project_role_to_assign in [ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
    #         can_invite = True
        
    #     if not can_invite:
    #         return Response({'error': f"As a {requester_role}, you do not have permission to invite a user with the role {project_role_to_assign}."}, status=status.HTTP_403_FORBIDDEN)
        
    #     if User.objects.filter(email__iexact=email_to_invite).exists():
    #         return Response({'error': 'A user with this email already exists. Please add them as a member directly.'}, status=status.HTTP_400_BAD_REQUEST)
    #     if Invitation.objects.filter(email__iexact=email_to_invite).exists():
    #         return Response({'error': 'An invitation for this email has already been sent.'}, status=status.HTTP_400_BAD_REQUEST)

    #     global_role_map = {
    #         ProjectMember.Role.MANAGER : User.Role.MANAGER,
    #         ProjectMember.Role.DEVELOPER: User.Role.DEVELOPER,
    #         ProjectMember.Role.TESTER: User.Role.TESTER,
    #     }
    #     global_role = global_role_map.get(project_role_to_assign, User.Role.DEVELOPER)

    #     invitation = Invitation.objects.create(
    #         email=email_to_invite, 
    #         role=global_role,
    #         invited_by=request.user
    #     )
    #     new_user = User.objects.create_user(
    #         email=invitation.email, password=None, role=invitation.role, is_active=False
    #     )
    #     ProjectMember.objects.create(project=project, user=new_user, role=project_role_to_assign)

    #     invitation_link = f"http://localhost:5173/set-password?token={invitation.token}"
    #     send_mail(
    #         subject=f'You are invited to join Project: {project.name}!',
    #         message=f"Hello, please click the link to set your password and join the project: {invitation_link}",
    #         from_email=settings.DEFAULT_FROM_EMAIL,
    #         recipient_list=[invitation.email],
    #     )
        
    #     return Response({
    #         'status': 'Invitation sent successfully. The user has been added to the project pending activation.'
    #     }, status=status.HTTP_201_CREATED)
    
    
    def _get_requester_role(self, user, project):
        try:
            member = ProjectMember.objects.get(project=project, user=user)
            return member.role
        except ProjectMember.DoesNotExist:
            return None

    def perform_update(self, serializer):
        project = serializer.instance.project
        new_role = serializer.validated_data.get("role")

        if new_role and new_role == ProjectMember.Role.MANAGER :
            if ProjectMember.objects.filter(project=project, role=ProjectMember.Role.MANAGER ).exclude(pk=serializer.instance.pk).exists():
                raise PermissionDenied("A Project Manager already exists for this project.")

        requester_role = self._get_requester_role(self.request.user, project)
        
        if new_role == ProjectMember.Role.OWNER:
            raise PermissionDenied("Cannot promote any member to Owner.")

        if requester_role == ProjectMember.Role.OWNER:
            pass 
        elif requester_role == ProjectMember.Role.MANAGER :
            original_role = serializer.instance.role
            if original_role not in [ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
                raise PermissionDenied("Project Managers can only manage Developers and Testers.")
            if new_role not in [ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
                 raise PermissionDenied("Project Managers can only assign roles of Developer or Tester.")
        else:
            raise PermissionDenied("You do not have permission to modify members of this project.")
            
        serializer.save()

    def perform_destroy(self, instance):
        project = instance.project
        role_to_delete = instance.role
        requester_role = self._get_requester_role(self.request.user, project)
        if requester_role == ProjectMember.Role.OWNER:
            if instance.user == self.request.user:
                raise PermissionDenied("Owners cannot remove themselves from a project.")
        elif requester_role == ProjectMember.Role.MANAGER :
            if role_to_delete not in [ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
                raise PermissionDenied("Project Managers can only remove Developers or Testers.")
        else:
            raise PermissionDenied("You do not have permission to remove members from this project.")
        instance.delete()
# class ManagedTeamMembersView(APIView):
#     """
#     An endpoint for a Project Manager to see a unique list of all users
#     who are members of the projects they manage.
#     """
#     permission_classes = [IsAuthenticated]

#     def get(self, request, *args, **kwargs):
#         current_user = request.user

#         # 1. Find the IDs of all projects where the current user is a Project Manager.
#         managed_project_ids = ProjectMember.objects.filter(
#             user=current_user,
#             role=ProjectMember.Role.MANAGER 
#         ).values_list('project_id', flat=True)

#         if not managed_project_ids.exists():
#             # If the user manages no projects, return an empty list.
#             return Response([])

#         # 2. Find the unique IDs of all users who are members of those projects,
#         #    excluding the manager themselves.
#         team_member_ids = ProjectMember.objects.filter(
#             project_id__in=managed_project_ids
#         ).exclude(
#             user=current_user
#         ).values_list('user_id', flat=True).distinct()

#         # 3. Fetch the full User objects for those IDs.
#         team_members = User.objects.filter(id__in=team_member_ids)

#         # 4. Serialize the user data and return it as the response.
#         serializer = UserSerializer(team_members, many=True)
#         return Response(serializer.data)

class ManagedTeamMembersView(APIView):
    """
    An endpoint for a Project Manager to see a unique list of all users
    who are members of the projects they manage.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        current_user = request.user

        # 1. Find the IDs of all projects where the current user is a Project Manager.
        managed_project_ids = ProjectMember.objects.filter(
            user=current_user,
            role=ProjectMember.Role.MANAGER 
        ).values_list('project_id', flat=True)

        if not managed_project_ids.exists():
            # If the user manages no projects, return an empty list.
            return Response([])

        # 2. Find the unique IDs of all users who are members of those projects,
        #    excluding the manager themselves.
        team_member_ids = ProjectMember.objects.filter(
            project_id__in=managed_project_ids,
            role__in=[ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]
        ).values_list('user_id', flat=True).distinct()

        # 3. Fetch the full User objects for those IDs.
        team_members = User.objects.filter(
            id__in=team_member_ids
        )
        # 4. Serialize the user data and return it as the response.
        serializer = UserSerializer(team_members, many=True)
        return Response(serializer.data)


class ProjectSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, project_id, format=None):
        # Ensure the user is a member of the project they are requesting
        if not ProjectMember.objects.filter(project_id=project_id, user=request.user).exists():
            return Response({"error": "You do not have permission to view this project."}, status=status.HTTP_403_FORBIDDEN)

        # 1. Date range calculations
        today = timezone.now()
        seven_days_ago = today - timedelta(days=7)

        # Base queryset for tasks in the current project
        project_tasks = Task.objects.filter(project_id=project_id)

        # 2. Summary Card Logic
        # For 'completed', we assume a status named 'Done'. Adjust if yours is different.
        completed_tasks_last_7_days = project_tasks.filter(
            status__title__iexact='Done', 
            updated_at__gte=seven_days_ago # Using updated_at as a proxy for completed_at
        ).count()

        summary_cards = {
            'completed': completed_tasks_last_7_days,
            'created': project_tasks.filter(created_at__gte=seven_days_ago).count(),
            'updated': project_tasks.filter(updated_at__gte=seven_days_ago).count(),
            'due_soon': project_tasks.filter(due_date__range=[today, today + timedelta(days=3)]).exclude(status__title__iexact='Done').count()
        }

        # 3. Status Overview Logic
        status_overview = project_tasks.values('status__title').annotate(count=Count('id')).order_by('status__title')

        # 4. Recent Activity Logic
        recent_activities = ActivityLog.objects.filter(project_id=project_id)[:10] # Get last 10 activities

        # 5. Assemble the final response
        response_data = {
            "summary_cards": summary_cards,
            "status_overview": {
                "total": project_tasks.count(),
                "breakdown": list(status_overview)
            },
            "recent_activity": ActivityLogSerializer(recent_activities, many=True).data
        }

        return Response(response_data)


class AcceptProjectInvitationView(APIView):
    """
    ENDPOINT 1: For an EXISTING, LOGGED-IN user to accept.
    """
    permission_classes = [IsAuthenticated] # User must be logged in

    def post(self, request, *args, **kwargs):
        token = request.data.get('token')
        if not token:
            return Response({'error': 'Token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invitation = ProjectInvitation.objects.get(token=token, status=ProjectInvitation.Status.PENDING)
        except ProjectInvitation.DoesNotExist:
            return Response({'error': 'Invalid or expired invitation token.'}, status=status.HTTP_404_NOT_FOUND)

        if invitation.email.lower() != request.user.email.lower():
            return Response({'error': 'This invitation is not for you.'}, status=status.HTTP_403_FORBIDDEN)
            
        if ProjectMember.objects.filter(project=invitation.project, user=request.user).exists():
            invitation.status = ProjectInvitation.Status.ACCEPTED
            invitation.save()
            return Response({'error': 'You are already a member of this project.'}, status=status.HTTP_400_BAD_REQUEST)

        # All checks passed. Add the user to the project.
        member = ProjectMember.objects.create(
            project=invitation.project,
            user=request.user,
            role=invitation.role
        )
        
        invitation.status = ProjectInvitation.Status.ACCEPTED
        invitation.save()

        serializer = ProjectMemberSerializer(member)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ActivateAndSetPasswordView(APIView):
    """
    ENDPOINT 2: For a NEW, INACTIVE user to set password and activate.
    """
    permission_classes = [AllowAny] # Anyone with a valid token can use this

    def post(self, request, *args, **kwargs):
        token = request.data.get('token')
        if not token:
            return Response({'error': 'Token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Verify token
        try:
            invitation = ProjectInvitation.objects.get(token=token, status=ProjectInvitation.Status.PENDING)
        except ProjectInvitation.DoesNotExist:
            return Response({'error': 'Invalid or expired invitation token.'}, status=status.HTTP_404_NOT_FOUND)

        # 2. Get the inactive user
        user = invitation.user_to_invite
        if not user or user.is_active:
             return Response({'error': 'This invitation is invalid or the user is already active.'}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Get and set password
        password = request.data.get('password')
        if not password:
             return Response({'error': 'Password is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        user.set_password(password)
        user.is_active = True
        user.save()

        # 4. Mark invitation as accepted
        invitation.status = ProjectInvitation.Status.ACCEPTED
        invitation.save()

        return Response({'status': 'Account activated and password set successfully.'}, status=status.HTTP_200_OK)