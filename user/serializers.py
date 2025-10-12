from rest_framework import serializers
from .models import User
from django.utils import timezone
import pytz
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
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

    last_login = serializers.SerializerMethodField()

    class Meta:
        model = User
        manager_name = 'objects'
        fields = ('id', 'email', 'first_name', 'last_name','phone' ,'is_active','role','last_login','is_deleted', 'deleted_at')
        read_only_fields = (['id','is_deleted', 'deleted_at'])
    
    def get_last_login(self, obj):
        """
        This method is called to get the value for the 'last_login' field.
        It converts the UTC time from the database to IST.
        """
        if not obj.last_login:
            return None
        
        # Define the Indian Standard Time timezone
        ist = pytz.timezone('Asia/Kolkata')
        
        # Convert the UTC datetime from the database to IST
        local_time = obj.last_login.astimezone(ist)
        
        # Format the IST datetime into a readable string
        return local_time.strftime('%Y-%m-%d %H:%M:%S %Z') # Example: "2025-10-01 16:21:53 IST"


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
        



class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Add custom claims
        token['email'] = user.email # You can add custom data to the token here if needed
        
        return token

    def validate(self, attrs):
        # The default result (access/refresh tokens)
        data = super().validate(attrs)

        # Get the user object
        user = self.user

        # Update the last_login field
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        
        return data
class AdminUserManagementSerializer(serializers.ModelSerializer):
    """Serializer for admins to create and update user accounts."""
    class Meta:
        model = User
        fields = ['id', 'email', 'first_name', 'last_name', 'role', 'phone', 'is_active']
        read_only_fields = ['id']

    def create(self, validated_data):
        validated_data['is_active'] = validated_data.get('is_active', False)
        user = User.objects.create(**validated_data)
        return user    

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    new_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    confirm_new_password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError("New passwords do not match.")
        return attrs

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user