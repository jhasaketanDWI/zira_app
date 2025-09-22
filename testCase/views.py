from rest_framework.response import Response
from rest_framework.decorators import action
from .models import TestCase
from rest_framework import viewsets, status, exceptions
from rest_framework.permissions import IsAuthenticated
from project.models import Project

from .serializers import(
    
     TestCaseSerializer, 
     TestCaseStatusUpdateSerializer,
    
     )


class TestCaseViewSet(viewsets.ModelViewSet):
    """
    API endpoint for Test Cases.

    - Create: `POST /api/testcases/`
    - List by Project: `GET /api/projects/{project_pk}/testcases/`
    - Update Status: `PUT /api/testcases/{pk}/status/`
    """
    queryset = TestCase.objects.all().select_related('project').order_by('-created_at')
    serializer_class = TestCaseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        If the view is accessed via a nested route from a project,
        this method filters the test cases for that specific project.
        """
        if 'project_pk' in self.kwargs:
            return self.queryset.filter(project_id=self.kwargs['project_pk'])
        return self.queryset

    def perform_create(self, serializer):
        """
        Overrides the default create behavior to handle project assignment
        and automatically set the source to 'MANUAL'.
        """
        project_id = None
        # Case 1: Called from a nested URL like /api/projects/{project_pk}/testcases/
        if 'project_pk' in self.kwargs:
            project_id = self.kwargs['project_pk']
        # Case 2: Called from /api/testcases/, project must be in request body
        elif 'project' in self.request.data:
            project_id = self.request.data['project']
        else:
            raise exceptions.ValidationError("Project ID must be provided.")

        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            raise exceptions.NotFound(f"Project with ID {project_id} not found.")

        serializer.save(
            source=TestCase.Source.MANUAL,
            project=project
        )

    @action(detail=True, methods=['put'], url_path='status', serializer_class=TestCaseStatusUpdateSerializer)
    def update_status(self, request, pk=None):
        """
        Custom action to update the status of a test case.
        Allows marking a test case as EXECUTED, BLOCKED, etc.
        Example: PUT /api/testcases/123/status/ with body {"status": "EXECUTED"}
        """
        test_case = self.get_object()
        serializer = self.get_serializer(test_case, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Return the full, updated test case representation for confirmation
        response_serializer = TestCaseSerializer(test_case)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
    
