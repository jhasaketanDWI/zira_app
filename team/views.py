from .models import  Team, TeamMember
from .serializers import(
     TeamListSerializer,
       TeamDetailSerializer, 
       TeamCreateSerializer, 
       TeamMemberSerializer,
         TeamInviteSerializer
     )
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework import viewsets, generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from user.models import User
from rest_framework.decorators import action

from common.permissions import IsOwnerAdminOrScrumMaster,RBACPermission
from .permissions import IsTeamAdmin


class TeamViewSet(viewsets.ModelViewSet):
    """
    A ViewSet for creating, viewing, and managing teams.
    - 'create': Creates a new team and invites members (Restricted).
    - 'retrieve': Shows team details (if user is an accepted member).
    - 'list': Returns teams the user is an accepted member of.
    """
    queryset = Team.objects.all()
    permission_classes = [IsAuthenticated,RBACPermission] # Base permission
    perms_map = {
        # Team Management
        'create': 'team.can_create_team',
        'update': 'team.can_edit_team',
        'partial_update': 'team.can_edit_team',
        'destroy': 'team.can_delete_team',
        
        # Viewing logic (RBAC + get_queryset handles the security)
        'list': 'team.can_view_all_teams',     # If user has this, they see ALL. If not, they see OWN.
        'retrieve': 'team.can_view_all_teams', # Same logic applies
        
        # Custom Action
        'invite_members': 'team.can_invite_team_members',
    }
    def get_queryset(self):
        """
        --- MODIFIED ---
        Overrides the queryset.
        - Global Owners/Admins see ALL teams.
        - Other users only see teams they are an "ACCEPTED" member of.
        """
        user = self.request.user
        if not user.is_authenticated:
            return Team.objects.none()
        
        if user.role in [User.Role.OWNER, User.Role.ADMIN]:
            # Admins/Owners get to see all teams
            return Team.objects.all().distinct()
        
        if user.has_perm('team.can_view_all_teams'):
            return Team.objects.all().distinct()
            

        return user.teams.filter(
            team_memberships__user=user,
            team_memberships__status=TeamMember.MemberStatus.ACCEPTED
        ).distinct()

    def get_serializer_class(self):
        """
        Return different serializers for different actions.
        """
        if self.action == 'create':
            return TeamCreateSerializer
        if self.action == 'retrieve':
            return TeamDetailSerializer
        return TeamListSerializer # For 'list' action

    def get_object(self):
        """
        --- MODIFIED ---
        Ensure user can 'retrieve' a team they are an accepted member of.
        - Admins/Owners can 'retrieve' ANY team.
        """
        user = self.request.user
        obj = get_object_or_404(Team.objects.all(), pk=self.kwargs.get('pk'))

        # Allow Admins/Owners to retrieve any team
        if user.role in [User.Role.OWNER, User.Role.ADMIN]:
            return obj
        if user.has_perm('team.can_view_all_teams'):
            return obj

        # Original logic for regular users
        if user.team_memberships.filter(
            team=obj, 
            status=TeamMember.MemberStatus.ACCEPTED
        ).exists():
            return obj
            
        raise Http404("You are not a member of this team.")

    def get_permissions(self):
        """
        Overrides the default permissions.
        - REQUIRES IsOwnerAdminOrScrumMaster to 'create' a team.
        - REQUIRES IsAuthenticated for all other actions.
        """
        if self.action == 'create':
            return [IsAuthenticated(),IsOwnerAdminOrScrumMaster()]
        
        return super().get_permissions()

    def create(self, request, *args, **kwargs):
        """
        Overrides the default create method to provide the
        custom response you asked for.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Get the lists saved by the serializer
        invited_emails = serializer.validated_data.get('successfully_invited_emails', [])
        # already_in_team_emails = serializer.validated_data.get('already_in_team_emails', [])
        
        # Build the custom response
        response_data = {
            "status": "Team created successfully.",
            "team_details": serializer.data, # Basic team info (name, about, id)
            "invitations_sent_to": invited_emails,
            # "users_already_in_team": already_in_team_emails
        }
        
        headers = self.get_success_headers(serializer.data)
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)
    
    @action(detail=True,methods=['post'],permission_classes=[IsAuthenticated, (IsTeamAdmin | IsOwnerAdminOrScrumMaster)],
        url_path='invite')
    def invite_members(self, request, pk=None):
        """
        An endpoint to invite new members to an existing team.
        Allowed for Team Admins OR global Owner/Admin/Scrum Masters.
        """
        team = self.get_object()
        
        serializer = TeamInviteSerializer(
            data=request.data,
            context={'team': team, 'request': request}
        )
        serializer.is_valid(raise_exception=True)
        
        invitation_data = serializer.save()

        response_data = {
            "status": "Invitations sent successfully.",
            "team_id": team.id,
            "team_name": team.name,
            **invitation_data
        }
        return Response(response_data, status=status.HTTP_200_OK)

class MyTeamInvitationsView(generics.ListAPIView):
    """
    An endpoint to show the current user all their PENDING team invitations.
    GET /api/teams/invitations/pending/
    """
    serializer_class = TeamMemberSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Returns all PENDING team memberships for the logged-in user."""
        return TeamMember.objects.filter(
            user=self.request.user,
            status=TeamMember.MemberStatus.PENDING
        ).select_related('team', 'invited_by')

class RespondToTeamInvitationView(APIView):
    """
    An endpoint for a user to ACCEPT or DECLINE a team invitation.
    POST /api/teams/invitations/<int:membership_id>/respond/
    
    Body:
    { "action": "accept" } or { "action": "decline" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, membership_id, *args, **kwargs):
        action = request.data.get('action')
        
        if action not in ['accept', 'decline']:
            return Response({'error': 'Invalid action. Must be "accept" or "decline".'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Find the specific pending invitation *for this user*
            membership = TeamMember.objects.get(
                id=membership_id,
                user=request.user,
                status=TeamMember.MemberStatus.PENDING
            )
        except TeamMember.DoesNotExist:
            return Response({'error': 'Invitation not found or already handled.'}, status=status.HTTP_404_NOT_FOUND)

        if action == 'accept':
            membership.status = TeamMember.MemberStatus.ACCEPTED
            membership.save()
            return Response({'status': f'Invitation to join {membership.team.name} accepted.'}, status=status.HTTP_200_OK)
        
        if action == 'decline':
            membership.status = TeamMember.MemberStatus.DECLINED
            membership.save()
            return Response({'status': f'Invitation to join {membership.team.name} declined.'}, status=status.HTTP_200_OK)
