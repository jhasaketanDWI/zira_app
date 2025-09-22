from rest_framework import serializers
from .models import TestCase

    
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


