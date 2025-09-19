from rest_framework import serializers
from .models import (
    User,
      SubscriptionPlan,
        Subscription, 
        Invoice, 
        TestCase, 
        Project,
        Project,
          ProjectMember,
            Epic,
              Sprint,
               Ticket)

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


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = ["id", "name", "description", "status", "owner", "created_at", "updated_at"]
        read_only_fields = ["owner"]

    def create(self, validated_data):
        """
        Ensure that the project is always created with the logged-in user as the owner.
        """
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["owner"] = request.user
        return Project.objects.create(**validated_data)

    def validate_owner(self, value):
        """
        Ensure the request.user is the same as the project owner 
        when creating or updating.
        """
        request = self.context.get("request")
        if request and request.method == "POST" and value != request.user:
            raise serializers.ValidationError(
                "You can only create projects as yourself (owner must be you)."
            )
        return value

    
    
class TestCaseSerializer(serializers.ModelSerializer):
    """
    Serializer for the TestCase model.
    Handles creation and listing of test cases. The 'project' is handled
    in the view to allow for creation via nested or non-nested routes.
    """
    # Use StringRelatedField for a human-readable representation of the project
    project = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = TestCase
        fields = [
            'id',
            'title',
            'steps',
            'expected_result',
            'project',
            'source',
            'status',
            'created_at',
            'updated_at'
        ]
        # Source is set automatically in the view, not by the user.
        read_only_fields = ['id', 'source', 'created_at', 'updated_at']

class TestCaseStatusUpdateSerializer(serializers.ModelSerializer):
    """
    A dedicated, lightweight serializer for updating only the status of a TestCase.
    Ensures that no other fields can be accidentally modified via the status endpoint.
    """
    class Meta:
        model = TestCase
        fields = ['status']


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = '__all__'


class SubscriptionSerializer(serializers.ModelSerializer):
    # The 'owner' field is made read-only because it's automatically assigned
    # to the logged-in user in the view, not sent in the request body.
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Subscription
        fields = '__all__'  


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = '__all__'
        


class ProjectMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectMember
        fields = "__all__"

class EpicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Epic
        fields = "__all__"

    def validate(self, data):
        
        project = data.get("project") or self.instance.project
        title = data.get("title") or self.instance.title

        if Epic.objects.filter(project=project, title__iexact=title).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError({"title": "Epic with this title already exists in this project."})

        return data
    
    

class SprintSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sprint
        fields = "__all__"

    def validate(self, data):
        
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({"end_date": "End date must be after start date."})

        return data
class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = "__all__"
