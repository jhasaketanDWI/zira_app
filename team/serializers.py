from rest_framework import serializers
from .models import  Team, TeamMember
from user.models import User, Invitation
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings

class TeamMemberUserSerializer(serializers.ModelSerializer):
    """A simple serializer to show basic user info (for nesting)."""
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'role']

class TeamMemberSerializer(serializers.ModelSerializer):
    """Serializer for displaying a single team member."""
    user = TeamMemberUserSerializer(read_only=True)
    team_name = serializers.CharField(source='team.name', read_only=True)

    class Meta:
        model = TeamMember
        fields = ['id', 'user', 'team', 'team_name', 'role', 'status']

class TeamDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for the 'Retrieve' view (GET /api/teams/<id>/).
    Shows all details and lists all members.
    """
    # This nested serializer fetches all members from the TeamMember table
    team_memberships = TeamMemberSerializer(many=True, read_only=True)
    created_by = TeamMemberUserSerializer(read_only=True)

    class Meta:
        model = Team
        fields = ['id', 'name', 'about', 'created_by', 'team_memberships']

class TeamListSerializer(serializers.ModelSerializer):
    """
    A simple serializer for the 'List' view (GET /api/teams/).
    --- MODIFIED ---
    - 'team_memberships' now only lists ACCEPTED members.
    """    
    member_count = serializers.SerializerMethodField()
     # This field will now be populated by the 'get_team_memberships' method
    team_memberships = serializers.SerializerMethodField()
    # team_memberships = TeamMemberSerializer(many=True, read_only=True)

    class Meta:
        model = Team
        fields = ['id', 'name', 'about', 'member_count', 'team_memberships']

    def get_member_count(self, obj):
        # Count only accepted members
        return obj.team_memberships.filter(status=TeamMember.MemberStatus.ACCEPTED).count()
    def get_team_memberships(self, obj):
        """
        --- NEW METHOD ---
        This method is called to populate the 'team_memberships' field.
        It filters for *only* ACCEPTED members.
        """
        # Filter for members with "ACCEPTED" status
        accepted_memberships = obj.team_memberships.filter(
            status=TeamMember.MemberStatus.ACCEPTED
        ).select_related('user') # Optimize DB query
        
        # Serialize that filtered list using the existing TeamMemberSerializer
        serializer = TeamMemberSerializer(
            accepted_memberships, 
            many=True, 
            read_only=True
        )
        return serializer.data

class TeamCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a new team (POST /api/teams/).
    This contains all your new logic.
    """
    members_to_invite = serializers.ListField(
        child=serializers.EmailField(),
        write_only=True,
        required=False,
        help_text="List of emails of *existing, active* users to invite."
    )


    class Meta:
        model = Team
        fields = ['id','name', 'about', 'members_to_invite']
        
    def validate_members_to_invite(self, emails):
        """
        Validates the list of emails.
        Checks that all users exist and are active.
        """
        if not emails:
            return []

        validated_users = []
        invalid_emails = []
        
        # Use set() to check each email only once
        for email in set(email.lower() for email in emails):
            try:
                # Check for registered AND active users
                user = User.objects.get(email__iexact=email, is_active=True)
                validated_users.append(user)
            except User.DoesNotExist:
                invalid_emails.append(email)

        # If any emails were bad, reject the entire request.
        if invalid_emails:
            raise serializers.ValidationError(
                f"The following users do not exist or are not active: {', '.join(invalid_emails)}"
            )
            
        # Return the list of validated User *objects*
        return validated_users

    def create(self, validated_data):
        """
        Creates the team and handles all invitations.
        This method is called by the view.
        """
        requesting_user = self.context['request'].user
        invited_users_list = validated_data.pop('members_to_invite', [])

        # These lists will be passed back to the view for the response
        self._validated_data['successfully_invited_emails'] = []
        self._validated_data['already_in_team_emails'] = []

        with transaction.atomic():
            # 1. Create the team
            team = Team.objects.create(
                created_by=requesting_user,
                organization=requesting_user.organization,
                **validated_data
            )

            # 2. Add the creator as the first member (as a Team Admin)
            TeamMember.objects.create(
                team=team,
                user=requesting_user,
                role=User.Role.ADMIN,  # Team creator is Admin of the team
                status=TeamMember.MemberStatus.ACCEPTED,
                invited_by=requesting_user
            )

            # 3. Process the list of users to invite
            for user_to_invite in invited_users_list:
                
                # Check if user is already in the team (including the creator)
                is_already_member = TeamMember.objects.filter(team=team, user=user_to_invite).exists()

                if is_already_member:
                    self._validated_data['already_in_team_emails'].append(user_to_invite.email)
                    continue

                # --- This is the "Smart Role" logic ---
                # The new member's team role matches their global role.
                team_role = user_to_invite.role
                
                # 4. Create the PENDING TeamMember invitation
                TeamMember.objects.create(
                    team=team,
                    user=user_to_invite,
                    role=team_role, # Set their smart role
                    status=TeamMember.MemberStatus.PENDING,
                    invited_by=requesting_user
                )

                # 5. Send email notification to the existing user
                send_mail(
                    subject=f"You've been invited to the '{team.name}' team!",
                    message=f"Hi {user_to_invite.first_name or user_to_invite.email},\n\n{requesting_user.email} has invited you to join their team.\n\nPlease log in to your account and check your pending invitations to accept.",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user_to_invite.email],
                )
                self._validated_data['successfully_invited_emails'].append(user_to_invite.email)

        return team


class TeamInviteSerializer(serializers.Serializer):
    """
    Serializer for inviting new members to an *existing* team.
    Used by the 'invite_members' custom action on the TeamViewSet.
    """
    members_to_invite = serializers.ListField(
        child=serializers.EmailField(),
        write_only=True,
        required=True,
        help_text="List of emails of *existing, active* users to invite."
    )

    def validate_members_to_invite(self, emails):
        """
        Validates the list of emails.
        (This logic is copied directly from your TeamCreateSerializer)
        """
        if not emails:
            return []

        validated_users = []
        invalid_emails = []
        
        for email in set(email.lower() for email in emails):
            try:
                user = User.objects.get(
                    email__iexact=email,
                    is_active=True,
                    organization=self.context['request'].user.organization
                )
                validated_users.append(user)
            except User.DoesNotExist:
                invalid_emails.append(email)

        if invalid_emails:
            raise serializers.ValidationError(
                f"The following users do not exist or are not active: {', '.join(invalid_emails)}"
            )
            
        return validated_users # Return user objects

    def save(self):
        """
        This custom .save() method creates the invitations.
        It's called by the view.
        """
        # Get data passed in from the view's context
        team = self.context['team']
        requesting_user = self.context['request'].user
        users_to_invite = self.validated_data['members_to_invite']

        successfully_invited_emails = []
        already_in_team_emails = []

        with transaction.atomic():
            for user_to_invite in users_to_invite:
                
                # Check if user is already in the team
                is_already_member = TeamMember.objects.filter(
                    team=team, 
                    user=user_to_invite
                ).exists()

                if is_already_member:
                    already_in_team_emails.append(user_to_invite.email)
                    continue

                # --- "Smart Role" logic ---
                team_role = user_to_invite.role
                
                # 4. Create the PENDING TeamMember invitation
                TeamMember.objects.create(
                    team=team,
                    user=user_to_invite,
                    role=team_role,
                    status=TeamMember.MemberStatus.PENDING,
                    invited_by=requesting_user
                )

                # 5. Send email notification
                send_mail(
                    subject=f"You've been invited to the '{team.name}' team!",
                    message=f"Hi {user_to_invite.first_name or user_to_invite.email},\n\n{requesting_user.email} has invited you to join their team.\n\nPlease log in to your account and check your pending invitations to accept.",
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user_to_invite.email],
                )
                successfully_invited_emails.append(user_to_invite.email)

        # Return the lists for the view's response
        return {
            "invitations_sent_to": successfully_invited_emails,
            "users_already_in_team": already_in_team_emails
        }