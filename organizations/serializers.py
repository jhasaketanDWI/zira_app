from rest_framework import serializers
from .models import Organization
from user.models import User
from project.models import Project
from django.db.models import Count

class OrganizationSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(read_only=True)
    project_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "domain",
            "description",
            "is_active",
            "is_protected",
            "created_at",
            "user_count",
            "project_count",
        ]

    def update(self, instance, validated_data):
        user = self.context["request"].user

        if not user.is_super_admin:
            validated_data.pop("is_protected", None)

        return super().update(instance, validated_data)