from rest_framework import serializers
from .models import User
#from .models import Invitation
#from common.permissions import IsOwnerUser

#Serailizers for invitation model (not applied for now, keep it commented)
"""class InvitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitation
        fields = ['email', 'role']

    def validate_role(self, value):
        # Ensure owner cannot invite another owner or admin
        if value in [User.Role.ADMIN, User.Role.OWNER]:
            raise serializers.ValidationError("Owners cannot invite Admins or other Owners.")
        return value

# Serializer for a new user to set their password
class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    token = serializers.UUIDField(required=True)

# Serializer for an owner to change a user's role
class UserRoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['role']
        
# This serializer is for safely displaying user data
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'role', 'created_at')
        read_only_fields = ('id', 'created_at')
"""

class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for displaying and updating user information.
    Excludes sensitive fields like the password.
    """
    class Meta:
        model = User
        # We only include safe fields to be returned or updated
        fields = ('id', 'email', 'first_name', 'last_name', 'role')
        # 'id' should be read-only.
        read_only_fields = (['id'])


class UserSignUpSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ('email', 'password', 'first_name', 'last_name', 'role')
        extra_kwargs = {
            'role': {'required': True}
        }

    def validate_role(self, value):

        if value == User.Role.ADMIN:
            raise serializers.ValidationError("Cannot create a user with the ADMIN role.")
        return value

    def create(self, validated_data):

        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            role=validated_data['role']
        )
        return user


class AdminSignUpSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ('email', 'password', 'first_name', 'last_name')

    def create(self, validated_data):

        user = User.objects.create_superuser(
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        return user

