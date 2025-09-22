from rest_framework import serializers
from .models import User

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

