# task/views.py

# ... (other imports)
from .models import ActivityLog # Make sure ActivityLog is imported

# ...

class TaskViewSet(viewsets.ModelViewSet):
    # ... (queryset, serializer_class, permission_classes, get_queryset are unchanged)

    # --- Helper method for partial updates (unchanged) ---
    def _update_task_field(self, request, pk, serializer_class):
        task = self.get_object()
        # Keep track of old values before saving for logging purposes
        old_values = {
            'status': task.status.title if task.status else None,
            'priority': task.priority
        }
        
        check_project_permission(request.user, task.project, allowed_roles=[])
        
        serializer = serializer_class(task, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Pass the old values along with the response for the logger
        response = Response(TaskSerializer(task, context={'request': request}).data, status=status.HTTP_200_OK)
        
        # Attach old values to the response object temporarily for logging
        response.old_values = old_values 
        return response
    
    # ... (perform_create, perform_update, etc. are unchanged)

    # --- Custom Actions for Partial Updates ---

    # 👇 MODIFIED: Consolidated and added logging
    @action(detail=True, methods=['patch'], url_path='status')
    def update_status(self, request, pk=None):
        """PATCH request to update only the task's status and log the activity."""
        task_before_update = self.get_object()
        old_status = task_before_update.status.title if task_before_update.status else "None"

        # Use the helper to perform the update
        response = self._update_task_field(request, pk, TaskStatusUpdateSerializer)
        
        # Fetch the instance again after it has been updated
        updated_task = self.get_object()
        new_status = updated_task.status.title

        # Create the activity log entry
        ActivityLog.objects.create(
            project=updated_task.project,
            task=updated_task,
            user=request.user,
            action_type='STATUS_UPDATE',
            details={
                'title': updated_task.title,
                'from_status': old_status,
                'to_status': new_status,
                'message': f"Task status changed from '{old_status}' to '{new_status}'."
            }
        )
        return response

    @action(detail=True, methods=['patch'], url_path='assignees')
    def update_assignees(self, request, pk=None):
        """PATCH request to update only the task's assignees."""
        return self._update_task_field(request, pk, TaskAssigneesUpdateSerializer)
        
    # ... (other update actions are unchanged) ...

    # 👇 MODIFIED: Added logging logic
    @action(detail=True, methods=['patch'], url_path='priority')
    def update_priority(self, request, pk=None):
        """PATCH request to update only the task's priority and log the activity."""
        task_before_update = self.get_object()
        old_priority = task_before_update.get_priority_display() # Gets the human-readable value

        # Use the helper to perform the update
        response = self._update_task_field(request, pk, TaskPriorityUpdateSerializer)
        
        # Fetch the instance again after it has been updated
        updated_task = self.get_object()
        new_priority = updated_task.get_priority_display()

        # Create the activity log entry
        ActivityLog.objects.create(
            project=updated_task.project,
            task=updated_task,
            user=request.user,
            action_type='PRIORITY_UPDATE',
            details={
                'title': updated_task.title,
                'from_priority': old_priority,
                'to_priority': new_priority,
                'message': f"Task priority changed from '{old_priority}' to '{new_priority}'."
            }
        )
        return response

    # ... (rest of the viewset methods)