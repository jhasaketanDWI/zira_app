from rest_framework import serializers
from .models import (Epic,Sprint, Ticket, Status, Task, Tag, Activity)
from project.models import ProjectMember
from common.models import Comment

class ActivitySerializer(serializers.ModelSerializer):
    comment_body = serializers.CharField(write_only=True)
    comment_details = serializers.SerializerMethodField()
    class Meta:
        model = Activity
        fields = [
            'id',
            'task',
            'actor',
            'created_at',
            'comment_details', 
            'comment_body'     
        ]
        read_only_fields = ['task', 'actor', 'created_at']
    
    def get_comment_details(self, obj):
        """Return the details of the linked comment."""
        if obj.comment:
            return {
                'id': obj.comment.id,
                'body': obj.comment.body,
                'author': obj.comment.author.get_full_name() if obj.comment.author else None,
                'datetime': obj.comment.created_at # The comment's own timestamp
            }
        return None
   
    def create(self, validated_data):
        """
        Handle the creation of both the Activity and the nested Comment.
        """
        # --- THIS IS THE FIX ---
        # Get the task and comment_body and REMOVE them from the dictionary
        task = validated_data.pop('task')
        comment_text = validated_data.pop('comment_body')
        
        current_user = self.context['request'].user

        # 1. Create the independent Comment object
        comment = Comment.objects.create(author=current_user, body=comment_text)

        # 2. Create the Activity that links the Task to the Comment
        # Now, validated_data does not contain 'task' or 'comment_body',
        # so it is safe to unpack.
        activity = Activity.objects.create(
            comment=comment,
            actor=current_user,
            task=task,
            **validated_data
        )
        return activity
    
    def update(self, instance, validated_data):
        """
        Handle updating the nested Comment's body when the Activity is updated.
        """
        if 'comment_body' in validated_data and instance.comment:
            comment_text = validated_data.pop('comment_body')
            instance.comment.body = comment_text
            instance.comment.save()

        return super().update(instance, validated_data)


class StatusSerializer(serializers.ModelSerializer):
    """
    Serializer for the Status model.
    """
    class Meta:
        model = Status
        fields = ['id', 'title']

class TaskSubtaskUpdateSerializer(serializers.ModelSerializer):
    parent_task = serializers.PrimaryKeyRelatedField(
        queryset=Task.objects.all(), required=True, allow_null=True
    )
    class Meta:
        model = Task
        fields = ['id','parent_task', 'title', 'status', 'priority', 'task_type']

    def validate_parent_task(self, value):
        """Prevent circular dependencies."""
        if value and value.pk == self.instance.pk:
            raise serializers.ValidationError("A task cannot be its own parent.")
        return value
class TaskSerializer(serializers.ModelSerializer):
    """
    Serializer for the Task model.
    Handles relationships with Project, Sprint, Epic, Assignee, Reporter, and Tags.
    """
    # Use nested serializers or StringRelatedField for better readability
    status = StatusSerializer(read_only=True)
    status_id = serializers.PrimaryKeyRelatedField(
        queryset=Status.objects.all(), source='status', write_only=True
    )
    assignees = serializers.PrimaryKeyRelatedField(
        queryset=ProjectMember.objects.all(), many=True, required=False
    )
    tags = serializers.PrimaryKeyRelatedField(many=True, queryset=Tag.objects.all(), required=False)

    reporter = serializers.PrimaryKeyRelatedField(
    queryset=ProjectMember.objects.all(),
    required=False, 
    allow_null=True)
    subtasks = TaskSubtaskUpdateSerializer(many=True, read_only=True)
    activity_log = ActivitySerializer(many=True, read_only=True)

    class Meta:
        model = Task
        fields = [
            'id', 'project', 'sprint', 'epic', 'title', 'description',
            'status', 'priority', 'task_type', 'status_id', 'assignees', 'reporter', 'tags',
            'due_date', 'story_points', 'subtasks', # Added new fields 'parent_task'
            'created_at', 'updated_at','activity_log'
        ]
        read_only_fields = ['created_at', 'updated_at', 'subtasks','epic']


    def to_representation(self, instance):
        """
        On read operations, serialize the full Tag objects instead of just their IDs.
        """
        from project.serializers import ProjectMemberSerializer
        representation = super().to_representation(instance)
        # Use TagSerializer to represent the tags
        representation['tags'] = TagSerializer(instance.tags.all(), many=True).data
        # show full assignee objects on GET requests
        representation['assignees'] = ProjectMemberSerializer(instance.assignees.all(), many=True).data
        return representation

    def validate(self, data):
        project = data.get('project') or (self.instance.project if self.instance else None)

        if not project:
            raise serializers.ValidationError({"project": "This field is required."})

        # Validate that related objects belong to the same project as the task
        for field_name in ['sprint', 'epic', 'reporter']:
            related_obj = data.get(field_name)
            if related_obj and related_obj.project != project:
                raise serializers.ValidationError({
                    field_name: f"{field_name.capitalize()} must belong to the same project as the task."
                })
        
        # Validate many-to-many relations (assignees) 
        # in serializers.py -> TaskSerializer -> validate()
        assignees = data.get('assignees')
        if assignees:
            for assignee in assignees:
                # This check is failing
                if assignee.project != project:
                    raise serializers.ValidationError({
                    "assignees": f"Assignee '{assignee.user.get_full_name()}' does not belong to this project."
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
        assignees_data = validated_data.pop('assignees', [])
        task = Task.objects.create(**validated_data)
        if tags_data:
            task.tags.set(tags_data)
        if assignees_data:
            task.assignees.set(assignees_data)
        return task

    def update(self, instance, validated_data):
        tags_data = validated_data.pop('tags', None)
        assignees_data = validated_data.pop('assignees', None)
        instance = super().update(instance, validated_data)

        if tags_data is not None:
            instance.tags.set(tags_data)
        if assignees_data is not None:
            instance.assignees.set(assignees_data)
        return instance
    
class SprintSerializer(serializers.ModelSerializer):
    # serialize them using TaskSerializer, and add them to a 'tasks' list.
    
    tasks = TaskSerializer(many=True, read_only=True)
    class Meta:
        model = Sprint
        fields = [
            'id', 'name', 'goal', 'project', 'start_date', 'end_date',
            'duration', 'epic', 'is_active', 'is_ended', 'tasks'
        ]
    def validate(self, data):
        
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({"end_date": "End date must be after start date."})

        return data

class EpicSerializer(serializers.ModelSerializer):
    sprints = SprintSerializer(many=True, read_only=True)

    class Meta:
        model = Epic
        fields = [
            'id', 'project', 'title', 'description', 'status', 'sprints'
            
        ]

    def validate(self, data):
        
        project = data.get("project") or self.instance.project
        title = data.get("title") or self.instance.title

        if Epic.objects.filter(project=project, title__iexact=title).exclude(id=self.instance.id if self.instance else None).exists():
            raise serializers.ValidationError({"title": "Epic with this title already exists in this project."})

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


    

class TaskStatusUpdateSerializer(serializers.ModelSerializer):
    """
    A specific serializer for only updating the status of a task.
    """
    class Meta:
        model = Task
        fields = ['status']

class TaskAssigneesUpdateSerializer(serializers.ModelSerializer):
    assignees = serializers.PrimaryKeyRelatedField(
        queryset=ProjectMember.objects.all(), many=True, required=False
    )
    class Meta:
        model = Task
        fields = ['assignees']

class TaskDescriptionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ['description']



class TaskDueDateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ['due_date']

class TaskStoryPointsUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ['story_points']

class TaskPriorityUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        fields = ['priority']

class TaskSprintUpdateSerializer(serializers.ModelSerializer):
    """
    A specific serializer for only updating the sprint of a task.
    Allows assigning a task to a sprint or removing it (by passing null).
    """
    sprint = serializers.PrimaryKeyRelatedField(
        queryset=Sprint.objects.all(),
        required=False,
        allow_null=True
    )

    class Meta:
        model = Task
        fields = ['sprint']

    def validate_sprint(self, value):
        """
        Check that the sprint belongs to the same project as the task.
        """
        if value and self.instance and value.project != self.instance.project:
            raise serializers.ValidationError("The selected sprint must belong to the same project as the task.")
        return value
    
    def update(self, instance, validated_data):
        """
        This method is called when serializer.save() is executed on an existing instance.
        We override it to add our custom epic-update logic.
        """
        # 'instance' is the task object being updated.
        # 'validated_data' contains the validated sprint object or None.
        new_sprint = validated_data.get('sprint', instance.sprint)
        
        # Determine the new epic based on the new sprint.
        new_epic = None
        if new_sprint:
            # If the new sprint has an associated epic, we'll use it.
            # If not, new_epic will correctly remain None.
            new_epic = new_sprint.epic

        # Update both the sprint and epic fields on the task instance.
        instance.sprint = new_sprint
        instance.epic = new_epic
        
        # Save the changes to the database.
        instance.save()
        
        return instance

# class ActivityLogEntrySerializer(serializers.Serializer):
#     """
#     Validates the structure of a new entry being added to the activity history.
#     """
#     type = serializers.CharField(max_length=100)
#     details = serializers.CharField()

#     def validate(self, data):
#         # You could add more complex validation here if needed
#         return data


