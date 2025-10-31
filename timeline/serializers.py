from rest_framework import serializers
from task.models import Epic, Task, Status
from project.models import Project

# --- Serializers for Fetching Timeline Data ---

class _TimelineTaskSerializer(serializers.ModelSerializer):
    """Read-only serializer for Tasks within the timeline."""
    status = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Task
        fields = ('id', 'title', 'start_date', 'due_date', 'status')
        read_only_fields = fields

class _TimelineEpicSerializer(serializers.ModelSerializer):
    """Read-only serializer for Epics, nesting related Tasks."""
    # Use the correct related_name from task/models.py
    tasks = _TimelineTaskSerializer(source='epic_tasks', many=True, read_only=True)

    class Meta:
        model = Epic
        fields = ('id', 'title', 'start_date', 'end_date', 'tasks')
        read_only_fields = fields

# --- Serializers for Updating Dates ---

class EpicDateUpdateSerializer(serializers.ModelSerializer):
    """Serializer specifically for updating Epic start/end dates via PATCH."""
    class Meta:
        model = Epic
        fields = ('start_date', 'end_date')

    def validate(self, data):
        start = data.get('start_date', getattr(self.instance, 'start_date', None))
        end = data.get('end_date', getattr(self.instance, 'end_date', None))
        if start and end and end < start:
            raise serializers.ValidationError("End date cannot be before the start date.")
        return data

class TaskDateUpdateSerializer(serializers.ModelSerializer):
    """Serializer specifically for updating Task start/due dates via PATCH."""
    class Meta:
        model = Task
        fields = ('start_date', 'due_date')

    def validate(self, data):
        start = data.get('start_date', getattr(self.instance, 'start_date', None))
        end = data.get('due_date', getattr(self.instance, 'due_date', None))
        if start and end and end < start:
            raise serializers.ValidationError("Due date cannot be before the start date.")
        return data

