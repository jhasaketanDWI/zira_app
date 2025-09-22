from rest_framework import serializers
from .models import (Epic,Sprint, Ticket, Task, Tag)



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



class TagSerializer(serializers.ModelSerializer):
    """
    Serializer for the Tag model.
    """
    class Meta:
        model = Tag
        fields = ['id', 'project', 'name', 'color', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, data):
        # On update, get the project from the instance if not provided
        project = data.get('project') or (self.instance.project if self.instance else None)
        name = data.get('name') or (self.instance.name if self.instance else None)

        if not project:
            raise serializers.ValidationError("Project is required.")
        
        # Check for unique tag name within the project
        query = Tag.objects.filter(project=project, name__iexact=name)
        if self.instance:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise serializers.ValidationError({"name": "A tag with this name already exists in this project."})
            
        return data


class TaskSerializer(serializers.ModelSerializer):
    """
    Serializer for the Task model.
    Handles relationships with Project, Sprint, Epic, Assignee, Reporter, and Tags.
    """
    # Use PrimaryKeyRelatedField for write operations to assign tags by ID
    tags = serializers.PrimaryKeyRelatedField(many=True, queryset=Tag.objects.all(), required=False)

    class Meta:
        model = Task
        fields = [
            'id', 'project', 'sprint', 'epic', 'title', 'description', 'due_date',
            'status', 'priority', 'task_type', 'assignee', 'reporter', 'tags',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def to_representation(self, instance):
        """
        On read operations, serialize the full Tag objects instead of just their IDs.
        """
        representation = super().to_representation(instance)
        # Use TagSerializer to represent the tags
        representation['tags'] = TagSerializer(instance.tags.all(), many=True).data
        return representation

    def validate(self, data):
        project = data.get('project') or (self.instance.project if self.instance else None)

        if not project:
            raise serializers.ValidationError({"project": "This field is required."})

        # Validate that related objects belong to the same project as the task
        for field_name in ['sprint', 'epic', 'assignee', 'reporter']:
            related_obj = data.get(field_name)
            if related_obj and related_obj.project != project:
                raise serializers.ValidationError({
                    field_name: f"{field_name.capitalize()} must belong to the same project as the task."
                })
        
        # Validate that tags belong to the same project
        tags = data.get('tags')
        if tags:
            for tag in tags:
                if tag.project != project:
                    raise serializers.ValidationError({
                        "tags": f"Tag '{tag.name}' does not belong to the selected project."
                    })

        return data

    def create(self, validated_data):
        tags_data = validated_data.pop('tags', [])
        task = Task.objects.create(**validated_data)
        if tags_data:
            task.tags.set(tags_data)
        return task

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        instance = super().update(instance, validated_data)

        if tags_data is not None:
            instance.tags.set(tags_data)
        return instance
