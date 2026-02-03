from django.core.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
from django.db.models import Q
from .models import (Project, ProjectMember, ProjectInvitation)
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated, AllowAny
from .serializers import (ProjectSerializer, ProjectMemberSerializer, ProjectDetailSerializer, ActivityLogSerializer,
                          _UserNestedSerializer, ProjectMemberBulkAssignByRoleSerializer, ProjectMemberInviteSerializer)
from rest_framework.views import APIView
from task.models import Task, ActivityLog
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count
from user.models import User, Invitation
from django.core.mail import send_mail
from django.conf import settings
from common.permissions import IsOwnerAdminOrManager, RBACPermission
from user.serializers import UserSerializer
from django.db import transaction
from django.shortcuts import get_object_or_404
from common.utils.email_service import send_notification_email, get_stakeholders_emails, get_all_project_members_emails


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by("-id")
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    perms_map = {
        'create': 'project.can_create_project',
        'update': 'project.can_edit_project_details',
        'partial_update': 'project.can_edit_project_details',
        'destroy': 'project.can_delete_project',

        # List/Retrieve are special: We rely on 'get_queryset' (membership)
        # instead of a specific global permission, so we leave them None
        # or map to a basic "can_view_project" if you enforced one.
        'list': None,
        'retrieve': None,

        # Custom Action
        'available_members': 'project.can_manage_project_members',
    }

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ProjectDetailSerializer
        return ProjectSerializer

    def get_queryset(self):
        user = self.request.user

        # Super admin sees all projects
        if user.is_super_admin:
            return Project.objects.all().order_by("-id")

        # Normal users see only projects inside their organization
        return Project.objects.filter(
            organization=user.organization
        ).filter(
            Q(owner=user) | Q(projectmember__user=user)
        ).distinct().order_by("-id")

    @transaction.atomic
    def perform_create(self, serializer):
        manager_to_assign = serializer.validated_data.get('MANAGER')

        # 1. Save the Project (Creator becomes the Project Owner)
        creator = self.request.user

        if (
                getattr(self.request.user, "role", None) == "OWNER"
                and self.request.user.organization is None
        ):
            raise PermissionDenied(
                "Owner must belong to an organization before creating a project."
            )
        # Assign project to creator's organization
        project = serializer.save(
            owner=creator,
            organization=creator.organization
        )

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
        # Only add OWNERS from the same organization
        org_owners = User.objects.filter(
            role='OWNER',
            organization=creator.organization
        ).exclude(id__in=users_to_exclude_ids)

        for owner in org_owners:
            members_to_create.append(
                ProjectMember(
                    user=owner,
                    project=project,
                    role=ProjectMember.Role.OWNER  # Assign the highest role for visibility
                )
            )
            users_to_exclude_ids.add(owner.id)  # Track ID to exclude from later queries

        # 3. Find all Scrum Masters
        # Only add SCRUM MASTERS from same organization
        scrum_masters = User.objects.filter(
            role='SCRUM_MASTER',
            organization=creator.organization
        ).exclude(id__in=users_to_exclude_ids)

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

        # --- [EMAIL INTEGRATION] New Project Created ---
        # Notify ALL users in the system that a new project exists
        # Only notify users in the project organization + super admins
        all_users = list(
            User.objects.filter(
                organization=project.organization,
                is_active=True
            ).values_list('email', flat=True)
        ) + list(
            User.objects.filter(is_super_admin=True).values_list('email', flat=True)
        )

        send_notification_email(
            subject=f"[New Project] {project.name} launched",
            recipients=list(all_users),
            template_path="emails/notification.html",
            context={
                'title': "New Project Created",
                'message_body': f"A new project '{project.name}' has been created by {creator.get_full_name()}.",
                'details': {
                    'Project Name': project.name,
                    'Key': project.id,
                    'Owner': creator.get_full_name()
                },
                'action_url': f"{settings.FRONTEND_URL}/projects/{project.id}"
            }
        )

    def perform_update(self, serializer):
        # RBAC Check is done. Now check Project Membership specific logic.
        project = self.get_object()
        try:
            member = ProjectMember.objects.get(project=project, user=self.request.user)
            # Only Project Owners or Managers can edit details (Business Logic)
            if member.role not in [ProjectMember.Role.OWNER, ProjectMember.Role.MANAGER]:
                raise PermissionDenied("You do not have permission to edit project details.")
        except ProjectMember.DoesNotExist:
            # Fallback for Global Admin/Owner who might not be in the member list but has permission
            if not (self.request.user.is_superuser or getattr(self.request.user, 'role', '') == 'OWNER'):
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
        RBAC: project.can_manage_project_members
        """
        project = self.get_object()
        try:
            requester_membership = ProjectMember.objects.get(project=project, user=request.user)
            requester_role = requester_membership.role
        except ProjectMember.DoesNotExist:
            # Allow global owners to pass if they aren't explicitly members
            if getattr(request.user, 'role', '') == 'OWNER':
                requester_role = ProjectMember.Role.OWNER
            else:
                return Response({"error": "You are not a member of this project."}, status=status.HTTP_403_FORBIDDEN)

        allowed_roles_to_query = []
        if requester_role == ProjectMember.Role.OWNER:
            allowed_roles_to_query = ['manager', 'developer', 'tester', 'scrum_master']
        elif requester_role == ProjectMember.Role.MANAGER:
            allowed_roles_to_query = ['developer', 'tester']
        elif requester_role == ProjectMember.Role.SCRUM_MASTER:
            allowed_roles_to_query = ['developer', 'tester', 'manager']

        if role.lower() not in allowed_roles_to_query:
            return Response({"error": f"As a {requester_role}, you cannot query for available {role}s."},
                            status=status.HTTP_403_FORBIDDEN)

        existing_member_ids = ProjectMember.objects.filter(project=project).values_list('user_id', flat=True)

        # Restrict available users to organization only
        available_users = User.objects.filter(
            organization=project.organization
        ).exclude(id__in=existing_member_ids)

        global_role_map = {'manager': 'MANAGER', 'developer': 'DEVELOPER', 'tester': 'TESTER',
                           'scrum_master': 'SCRUM_MASTER'}
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
    permission_classes = [IsAuthenticated, RBACPermission]
    perms_map = {
        'create': 'project.can_manage_project_members',
        'update': 'project.can_manage_project_members',
        'partial_update': 'project.can_manage_project_members',
        'destroy': 'project.can_manage_project_members',

        'list': None,  # Visible to project members (filtered in get_queryset)
        'retrieve': None,

        # Custom Actions
        'bulk_assign': 'project.can_manage_project_members',
        'invite_member': 'project.can_invite_member',  # Specific permission for invites
    }

    def get_queryset(self):
        project_pk = self.kwargs.get('project_pk')
        user = self.request.user

        # Super admin sees all members of this project regardless of org
        if user.is_super_admin:
            return ProjectMember.objects.filter(project_id=project_pk).order_by('-id')

        if not project_pk:
            return ProjectMember.objects.none()

        # Check membership
        try:
            requester_membership = ProjectMember.objects.get(project_id=project_pk, user=user)
            requester_role = requester_membership.role
        except ProjectMember.DoesNotExist:
            # Allow Global Owner view access
            if getattr(user, 'role', '') == 'OWNER':
                requester_role = ProjectMember.Role.OWNER
            else:
                return ProjectMember.objects.none()

        base_queryset = ProjectMember.objects.filter(
            project_id=project_pk,
            project__organization=user.organization  # enforce org boundary
        )

        # Filtering logic based on role
        if requester_role == ProjectMember.Role.MANAGER:
            return base_queryset.filter(
                role__in=[ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]
            ).order_by('-id')

        return base_queryset.exclude(user=user).order_by('-id')

    def perform_create(self, serializer):
        # RBAC Check 'can_manage_project_members' passed.
        # Now enforcing hierarchical business rules.
        project_pk = self.kwargs.get('project_pk')
        project = get_object_or_404(Project, pk=project_pk)

        role_to_assign = serializer.validated_data["role"]
        requester_role = self._get_requester_role(self.request.user, project)

        if not requester_role and getattr(self.request.user, 'role', '') == 'OWNER':
            requester_role = ProjectMember.Role.OWNER

        if requester_role == ProjectMember.Role.OWNER:
            if role_to_assign == ProjectMember.Role.OWNER:
                raise PermissionDenied("Cannot assign another Owner.")
        elif requester_role == ProjectMember.Role.MANAGER:
            if role_to_assign not in [ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
                raise PermissionDenied("Project Managers can only assign Developers or Testers.")
        else:
            raise PermissionDenied("You do not have permission to add members to this project.")

        member = serializer.save(project=project)

        # --- [EMAIL INTEGRATION] New Member Added ---
        # Notify existing project members
        recipients = get_all_project_members_emails(project)
        send_notification_email(
            subject=f"[{project.name}] Welcome {member.user.get_full_name()}",
            recipients=recipients,
            template_path="emails/notification.html",
            context={
                'title': "New Team Member Added",
                'message_body': f"{member.user.get_full_name()} has joined the project team.",
                'details': {
                    'New Member': member.user.get_full_name(),
                    'Role': member.role,
                    'Project': project.name,
                    'Added By': self.request.user.get_full_name()
                }
            }
        )

    @action(detail=False, methods=['post'], url_path='bulk-assign/(?P<role>[a-zA-Z_]+)')
    def bulk_assign(self, request, role, project_pk=None):
        # RBAC: 'project.can_manage_project_members'
        project = get_object_or_404(Project, pk=project_pk)
        role_to_assign = role.upper()

        if role_to_assign not in ProjectMember.Role.values:
            return Response({"error": f"'{role}' is not a valid role."}, status=status.HTTP_400_BAD_REQUEST)

        requester_role = self._get_requester_role(self.request.user, project)
        if not requester_role and getattr(request.user, 'role', '') == 'OWNER':
            requester_role = ProjectMember.Role.OWNER

        can_assign = False
        if requester_role == ProjectMember.Role.OWNER and role_to_assign != ProjectMember.Role.OWNER:
            can_assign = True
        elif requester_role == ProjectMember.Role.MANAGER and role_to_assign in [ProjectMember.Role.DEVELOPER,
                                                                                 ProjectMember.Role.TESTER]:
            can_assign = True

        if not can_assign:
            return Response({'error': f"As a {requester_role}, you cannot assign the role {role_to_assign}."},
                            status=status.HTTP_403_FORBIDDEN)

        serializer = ProjectMemberBulkAssignByRoleSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_ids = serializer.validated_data['user_ids']
        success_responses = []
        error_responses = []
        new_members = []

        for user_id in user_ids:
            if ProjectMember.objects.filter(project=project, user_id=user_id).exists():
                error_responses.append({'user_id': user_id, 'error': "This user is already a member."})
                continue
            try:
                user = User.objects.get(pk=user_id)
                member = ProjectMember.objects.create(project=project, user=user, role=role_to_assign)
                success_responses.append(ProjectMemberSerializer(member).data)
                new_members.append(user.get_full_name())
            except User.DoesNotExist:
                error_responses.append({'user_id': user_id, 'error': "User not found."})
        # --- [EMAIL INTEGRATION] Bulk Add Notification ---
        if new_members:
            recipients = get_all_project_members_emails(project)
            send_notification_email(
                subject=f"[{project.name}] {len(new_members)} New Members Added",
                recipients=recipients,
                template_path="emails/notification.html",
                context={
                    'title': "Team Members Added",
                    'message_body': f"The following users have been added to the project as {role_to_assign}s:",
                    'details': {
                        'Project': project.name,
                        'New Members': ", ".join(new_members),
                        'Added By': request.user.get_full_name()
                    }
                }
            )
        return Response({
            "assigned_members": success_responses,
            "failed_assignments": error_responses
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='invite-member')
    def invite_member(self, request, project_pk=None):
        """
        RBAC: 'project.can_invite_member'
        """
        project = get_object_or_404(Project, pk=project_pk)

        requester_role = self._get_requester_role(self.request.user, project)
        if not requester_role and getattr(request.user, 'role', '') == 'OWNER':
            requester_role = ProjectMember.Role.OWNER

        if not requester_role:
            return Response({"error": "You don't have permission to invite others to this project."},
                            status=status.HTTP_403_FORBIDDEN)

        serializer = ProjectMemberInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email_to_invite = serializer.validated_data['email']
        project_role_to_assign = serializer.validated_data['role']

        # Permission Check (Business Logic)
        can_invite = False
        if requester_role == ProjectMember.Role.OWNER and project_role_to_assign in [ProjectMember.Role.MANAGER,
                                                                                     ProjectMember.Role.SCRUM_MASTER,
                                                                                     ProjectMember.Role.DEVELOPER,
                                                                                     ProjectMember.Role.TESTER]:
            can_invite = True
        elif requester_role == ProjectMember.Role.MANAGER and project_role_to_assign in [ProjectMember.Role.DEVELOPER,
                                                                                         ProjectMember.Role.TESTER]:
            can_invite = True

        if not can_invite:
            return Response({
                                'error': f"As a {requester_role}, you do not have permission to invite a user with the role {project_role_to_assign}."},
                            status=status.HTTP_403_FORBIDDEN)

        if ProjectMember.objects.filter(project=project, user__email__iexact=email_to_invite).exists():
            return Response({'error': 'This user is already a member of this project.'},
                            status=status.HTTP_400_BAD_REQUEST)

        if ProjectInvitation.objects.filter(project=project, email__iexact=email_to_invite,
                                            status=ProjectInvitation.Status.PENDING).exists():
            return Response({'error': 'An invitation has already been sent to this email address.'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Only existing users from same organization can be invited
        existing_user = User.objects.filter(
            email__iexact=email_to_invite,
            organization=project.organization
        ).first()

        if existing_user:
            # Case 1: Existing User
            invitation = ProjectInvitation.objects.create(
                project=project,
                email=email_to_invite,
                role=project_role_to_assign,
                invited_by=request.user,
                user_to_invite=existing_user
            )
            accept_link = f"https://kanban.dreamwaveinnovations.com/accept-project-invite?token={invitation.token}"

            send_notification_email(
                subject=f"Invitation to join project: {project.name}",
                recipients=[email_to_invite],
                template_path="emails/notification.html",
                context={
                    'title': "You have been invited!",
                    'message_body': f"Hello {existing_user.first_name}, you have been invited to join the project '{project.name}'.",
                    'details': {
                        'Project': project.name,
                        'Role': project_role_to_assign,
                        'Invited By': request.user.get_full_name()
                    },
                    'action_url': accept_link
                }
            )
            return Response({'status': 'Invitation sent to existing user.'}, status=status.HTTP_201_CREATED)
        else:
            # Case 2: New User
            global_role_map = {
                ProjectMember.Role.MANAGER: User.Role.MANAGER,
                ProjectMember.Role.DEVELOPER: User.Role.DEVELOPER,
                ProjectMember.Role.TESTER: User.Role.TESTER,
                ProjectMember.Role.SCRUM_MASTER: User.Role.SCRUM_MASTER,
            }
            global_role = global_role_map.get(project_role_to_assign, User.Role.DEVELOPER)

            new_user = User.objects.create_user(
                email=email_to_invite,
                password=None,
                role=global_role,
                is_active=False,
                organization=project.organization
            )

            # NOTE: We create the member entry immediately for new users in your logic
            ProjectMember.objects.create(project=project, user=new_user, role=project_role_to_assign)

            invitation = ProjectInvitation.objects.create(
                project=project,
                email=email_to_invite,
                role=project_role_to_assign,
                invited_by=request.user,
                user_to_invite=new_user,
                status=ProjectInvitation.Status.PENDING
            )

            set_password_link = f"https://kanban.dreamwaveinnovations.com/set-password?token={invitation.token}"

            send_notification_email(
                subject=f"Welcome! Invitation to join project: {project.name}",
                recipients=[email_to_invite],
                template_path="emails/notification.html",
                context={
                    'title': "Welcome to the Team",
                    'message_body': f"You have been invited to join '{project.name}'. Please activate your account.",
                    'details': {
                        'Project': project.name,
                        'Role': project_role_to_assign,
                        'Invited By': request.user.get_full_name()
                    },
                    'action_url': set_password_link
                }
            )
            return Response({'status': 'Invitation sent. New user created and added to project.'},
                            status=status.HTTP_201_CREATED)

        # if existing_user:
        #     # Case 1: Existing User
        #     invitation = ProjectInvitation.objects.create(
        #         project=project,
        #         email=email_to_invite,
        #         role=project_role_to_assign,
        #         invited_by=request.user,
        #         user_to_invite=existing_user
        #     )
        #     accept_link = f"https://kanban.dreamwaveinnovations.com/accept-project-invite?token={invitation.token}"
        #     subject = f"You are invited to join Project: {project.name}"
        #     message = (
        #         f"Hello {existing_user.first_name or existing_user.email},\n\n"
        #         f"You've been invited to join the project '{project.name}' as a {project_role_to_assign}.\n"
        #         f"Please click the link to accept: {accept_link}"
        #     )
        #     send_mail(subject=subject, message=message, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[email_to_invite])

        #     return Response({'status': 'Invitation sent to existing user.'}, status=status.HTTP_201_CREATED)
        # else:
        #     # Case 2: New User
        #     global_role_map = {
        #         ProjectMember.Role.MANAGER: User.Role.MANAGER,
        #         ProjectMember.Role.DEVELOPER: User.Role.DEVELOPER,
        #         ProjectMember.Role.TESTER: User.Role.TESTER,
        #         ProjectMember.Role.SCRUM_MASTER: User.Role.SCRUM_MASTER,
        #     }
        #     global_role = global_role_map.get(project_role_to_assign, User.Role.DEVELOPER)

        #     new_user = User.objects.create_user(
        #         email=email_to_invite,
        #         password=None,
        #         role=global_role,
        #         is_active=False
        #     )

        #     ProjectMember.objects.create(project=project, user=new_user, role=project_role_to_assign)

        #     invitation = ProjectInvitation.objects.create(
        #         project=project,
        #         email=email_to_invite,
        #         role=project_role_to_assign,
        #         invited_by=request.user,
        #         user_to_invite=new_user,
        #         status=ProjectInvitation.Status.PENDING
        #     )

        #     set_password_link = f"https://kanban.dreamwaveinnovations.com/set-password?token={invitation.token}"
        #     subject = f"You are invited to join Project: {project.name}"
        #     message = (
        #         f"Hello,\n\n"
        #         f"You've been invited to join the project '{project.name}'.\n"
        #         f"Please click the link to set your password and activate your account: {set_password_link}"
        #     )
        #     send_mail(subject=subject, message=message, from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[email_to_invite])

        #     return Response({'status': 'Invitation sent. New user created and added to project.'}, status=status.HTTP_201_CREATED)

    def _get_requester_role(self, user, project):
        try:
            member = ProjectMember.objects.get(project=project, user=user)
            return member.role
        except ProjectMember.DoesNotExist:
            return None

    def perform_update(self, serializer):
        # RBAC: 'project.can_manage_project_members' check passed
        project = serializer.instance.project
        new_role = serializer.validated_data.get("role")

        if new_role and new_role == ProjectMember.Role.MANAGER:
            if ProjectMember.objects.filter(project=project, role=ProjectMember.Role.MANAGER).exclude(
                    pk=serializer.instance.pk).exists():
                raise PermissionDenied("A Project Manager already exists for this project.")

        requester_role = self._get_requester_role(self.request.user, project)
        if not requester_role and getattr(self.request.user, 'role', '') == 'OWNER':
            requester_role = ProjectMember.Role.OWNER

        if new_role == ProjectMember.Role.OWNER:
            raise PermissionDenied("Cannot promote any member to Owner.")

        if requester_role == ProjectMember.Role.OWNER:
            pass
        elif requester_role == ProjectMember.Role.MANAGER:
            original_role = serializer.instance.role
            if original_role not in [ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
                raise PermissionDenied("Project Managers can only manage Developers and Testers.")
            if new_role not in [ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
                raise PermissionDenied("Project Managers can only assign roles of Developer or Tester.")
        else:
            raise PermissionDenied("You do not have permission to modify members of this project.")

        serializer.save()

    def perform_destroy(self, instance):
        # RBAC: 'project.can_manage_project_members' check passed
        project = instance.project
        role_to_delete = instance.role
        user_name = instance.user.get_full_name()
        user_email = instance.user.email
        requester_role = self._get_requester_role(self.request.user, project)

        if not requester_role and getattr(self.request.user, 'role', '') == 'OWNER':
            requester_role = ProjectMember.Role.OWNER

        if requester_role == ProjectMember.Role.OWNER:
            if instance.user == self.request.user:
                raise PermissionDenied("Owners cannot remove themselves from a project.")
        elif requester_role == ProjectMember.Role.MANAGER:
            if role_to_delete not in [ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]:
                raise PermissionDenied("Project Managers can only remove Developers or Testers.")
        else:
            raise PermissionDenied("You do not have permission to remove members from this project.")
        recipients = get_all_project_members_emails(project)
        send_notification_email(
            subject=f"[{project.name}] Member Removed: {user_name}",
            recipients=recipients,
            template_path="emails/notification.html",
            context={
                'title': "Team Member Removed",
                'message_body': f"{user_name} ({user_email}) has been removed from the project.",
                'details': {
                    'Project': project.name,
                    'Removed Member': user_name,
                    'Removed By': self.request.user.get_full_name()
                }
            }
        )
        instance.delete()


class ManagedTeamMembersView(APIView):
    """
    An endpoint for a Project Manager to see a unique list of all users
    who are members of the projects they manage.
    """
    permission_classes = [IsAuthenticated, RBACPermission]
    perms_map = {
        'retrieve': 'project.can_manage_project_members'
    }

    def get(self, request, *args, **kwargs):
        # Your existing logic
        current_user = request.user
        managed_project_ids = ProjectMember.objects.filter(
            user=current_user,
            role=ProjectMember.Role.MANAGER
        ).values_list('project_id', flat=True)

        if not managed_project_ids.exists():
            return Response([])

        team_member_ids = ProjectMember.objects.filter(
            project_id__in=managed_project_ids,
            role__in=[ProjectMember.Role.DEVELOPER, ProjectMember.Role.TESTER]
        ).values_list('user_id', flat=True).distinct()

        team_members = User.objects.filter(id__in=team_member_ids)
        serializer = UserSerializer(team_members, many=True)
        return Response(serializer.data)


class ProjectSummaryView(APIView):
    permission_classes = [IsAuthenticated, RBACPermission]
    perms_map = {
        'retrieve': 'project.can_view_project_settings'  # Or can_view_project
    }

    def get(self, request, project_id, format=None):
        project = get_object_or_404(Project, pk=project_id)

        # Org boundary enforcement
        if not request.user.is_super_admin and project.organization != request.user.organization:
            return Response(
                {"error": "You do not have permission to view this project."},
                status=status.HTTP_403_FORBIDDEN
            )

        today = timezone.now()
        seven_days_ago = today - timedelta(days=7)
        project_tasks = Task.objects.filter(project_id=project_id)

        completed_tasks_last_7_days = project_tasks.filter(
            status__title__iexact='Done',
            updated_at__gte=seven_days_ago
        ).count()

        summary_cards = {
            'completed': completed_tasks_last_7_days,
            'created': project_tasks.filter(created_at__gte=seven_days_ago).count(),
            'updated': project_tasks.filter(updated_at__gte=seven_days_ago).count(),
            'due_soon': project_tasks.filter(due_date__range=[today, today + timedelta(days=3)]).exclude(
                status__title__iexact='Done').count()
        }

        status_overview = project_tasks.values('status__title').annotate(count=Count('id')).order_by('status__title')
        recent_activities = ActivityLog.objects.filter(project_id=project_id)[:10]

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
    permission_classes = [IsAuthenticated]  # User must be logged in

    def post(self, request, *args, **kwargs):
        token = request.data.get('token')
        if not token:
            return Response({'error': 'Token is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invitation = ProjectInvitation.objects.get(token=token, status=ProjectInvitation.Status.PENDING)
            # Org boundary check
            if (
                    not request.user.is_super_admin and
                    invitation.project.organization != request.user.organization
            ):
                return Response(
                    {'error': 'You cannot accept an invitation from another organization.'},
                    status=status.HTTP_403_FORBIDDEN
                )

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

        # --- [EMAIL INTEGRATION] Existing User Joined ---
        # Notify project members that the user accepted and joined
        recipients = get_all_project_members_emails(invitation.project)
        send_notification_email(
            subject=f"[{invitation.project.name}] New Member Joined: {request.user.get_full_name()}",
            recipients=recipients,
            template_path="emails/notification.html",
            context={
                'title': "Team Member Joined",
                'message_body': f"{request.user.get_full_name()} has accepted the invitation and joined the project.",
                'details': {
                    'Member': request.user.get_full_name(),
                    'Role': member.role,
                    'Project': invitation.project.name
                }
            }
        )

        serializer = ProjectMemberSerializer(member)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ActivateAndSetPasswordView(APIView):
    """
    ENDPOINT 2: For a NEW, INACTIVE user to set password and activate.
    """
    permission_classes = [AllowAny]  # Anyone with a valid token can use this

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
            return Response({'error': 'This invitation is invalid or the user is already active.'},
                            status=status.HTTP_400_BAD_REQUEST)

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

        # --- [EMAIL INTEGRATION] New User Activated/Joined ---
        # Notify project members that the NEW user has set password and officially joined
        recipients = get_all_project_members_emails(invitation.project)
        send_notification_email(
            subject=f"[{invitation.project.name}] New Member Activated: {user.get_full_name()}",
            recipients=recipients,
            template_path="emails/notification.html",
            context={
                'title': "Team Member Activated",
                'message_body': f"{user.get_full_name()} has set their password and is now active in the project.",
                'details': {
                    'Member': user.get_full_name(),
                    'Role': invitation.role,
                    'Project': invitation.project.name
                }
            }
        )

        return Response({'status': 'Account activated and password set successfully.'}, status=status.HTTP_200_OK)