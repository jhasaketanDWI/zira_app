from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import viewsets, status, exceptions
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Max


from task.permissions import IsProjectMember
from .tasks import execute_test_run  # celery task (see tasks.py)
from project.models import Project
from .models import (Module, TestSuite, QaTestCase, 
                     TestRun, TestExecution, TestPlan,
                     Environment, TestStep, TestTemplate,
                     TemplateStep)
from .serializers import (
    ModuleSerializer, TestSuiteSerializer, TestCaseSerializer,
    TestRunSerializer, TestExecutionSerializer, TestPlanSerializer, EnvironmentSerializer,
    SimpleModuleSerializer, SimpleModuleWithCasesSerializer, TestStepSerializer,
    TestTemplateSerializer, TemplateStepSerializer
)




class ModuleViewSet(viewsets.ModelViewSet):
    queryset = Module.objects.all().prefetch_related(
        "children",
        "testcases",
        "testcases__steps"
    ).order_by("id")
    serializer_class = ModuleSerializer
    # permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Optionally filter modules by ?project=<id>
        and return only root modules by default.
        """
        qs = super().get_queryset()

        root_only_actions = ["list", "simplified_list", "tree", "tree_with_cases"]

        if self.action not in root_only_actions:
            return qs
        qs = qs.filter(parent__isnull=True)
        
        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs

    def perform_create(self, serializer):
        
        serializer.save(created_by=self.request.user)
    
    def perform_update(self, serializer):
        allowed_fields = {"name", "description", "parent"}

        # Keys the client is trying to update
        incoming_fields = set(serializer.validated_data.keys())

        disallowed = incoming_fields - allowed_fields
        if disallowed:
            raise ValidationError(
                {"detail": f"You cannot update these fields: {', '.join(disallowed)}"}
            )
        serializer.save()
    
    def destroy(self, request, *args, **kwargs):
        module = self.get_object()

        # Block if there are child modules
        if module.children.exists():
            raise ValidationError({
                "detail": "Cannot delete module while it still has child modules. "
                          "Delete child modules first."
            })
        # Block if there are test cases directly attached to this module
        if module.testcases.exists():
            raise ValidationError({
                "detail": "Cannot delete module while it still has test cases. "
                          "Delete or move those test cases first."
            })
        # Block if there are suites under this module
        if module.suites.exists():
            raise ValidationError({
                "detail": "Cannot delete module while it still has test suites. "
                          "Delete or move those suites first."
            })
        return super().destroy(request, *args, **kwargs)


    @action(detail=False, methods=["get"], url_path="simple-modules-cases")
    def tree_with_cases(self, request):
        """
        Return module tree (root + children recursively)with test cases under each module.Each module -> {id, name, children, testcases[id, title]}."""
        
        qs = self.get_queryset()  # already filtered to root modules + optional project
        serializer = SimpleModuleWithCasesSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="simple-modules")
    def tree(self, request):
        """Return module tree (root + children recursively)without test cases.
        Each module -> {id, name, children}.
        """
        qs = self.get_queryset()  # already filtered to root modules + optional project
        serializer = SimpleModuleSerializer(qs, many=True)
        return Response(serializer.data)
    


class TestSuiteViewSet(viewsets.ModelViewSet):
    queryset = TestSuite.objects.all()
    serializer_class = TestSuiteSerializer

    @action(detail=True, methods=["post"])
    def add_case(self, request, pk=None):
        suite = self.get_object()
        data = request.data.copy()
        data["suite"] = suite.id
        serializer = TestCaseSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        case = serializer.save()
        return Response(TestCaseSerializer(case).data, status=status.HTTP_201_CREATED)
    
    def perform_update(self, serializer):
        allowed_fields = {
            "name","description",
            "module",
        }
        incoming = set(serializer.validated_data.keys())
        disallowed = incoming - allowed_fields

        if disallowed:
            raise ValidationError({
                "detail": f"You cannot update these fields: {', '.join(disallowed)}"
            })
        serializer.save()
    
    def destroy(self, request, *args, **kwargs):
        suite = self.get_object()

        # block deletion if there are cases in this suite
        if suite.cases.exists():
            raise ValidationError({
                "detail": "Cannot delete suite while it still has test cases. "
                          "Delete or move those cases first."
            })
        return super().destroy(request, *args, **kwargs)



class TestCaseViewSet(viewsets.ModelViewSet):
    queryset = QaTestCase.objects.all()
    serializer_class = TestCaseSerializer

    def perform_update(self, serializer):
        # Allow only these fields to be updated
        allowed_fields = {
            "title","preconditions","expected_result",
            "priority","status","labels","severity",
            "module","natural_language","steps",
        }
        incoming = set(serializer.validated_data.keys())
        disallowed = incoming - allowed_fields

        if disallowed:
            raise ValidationError({
                "detail": f"You cannot update these fields: {', '.join(disallowed)}"
            })
        serializer.save()



class TestStepViewSet(viewsets.ModelViewSet):
    """
    CRUD API for TestStep.
    Base URL (after router): /testcase/steps/
    """
    queryset = TestStep.objects.all().order_by("order", "id")
    serializer_class = TestStepSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Optional: filter by case id: /testcase/steps/?case=<case_id>
        case_id = self.request.query_params.get("case")
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs

    def perform_create(self, serializer):
        """
        If 'order' is not provided, automatically put the step
        at the end for that case.
        """
        case = serializer.validated_data["case"]
        order = serializer.validated_data.get("order")

        if order is None:
            last_order = TestStep.objects.filter(case=case).aggregate(
                Max("order")
            )["order__max"] or 0
            serializer.save(order=last_order + 1)
        else:
            serializer.save()


class TestTemplateViewSet(viewsets.ModelViewSet):
    queryset = TestTemplate.objects.all()
    serializer_class = TestTemplateSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class TemplateStepViewSet(viewsets.ModelViewSet):
    queryset = TemplateStep.objects.all().order_by("order", "id")
    serializer_class = TemplateStepSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        template_id = self.request.query_params.get("template")
        if template_id:
            qs = qs.filter(template_id=template_id)
        return qs


class TestPlanViewSet(viewsets.ModelViewSet):
    queryset = TestPlan.objects.all()
    serializer_class = TestPlanSerializer

class EnvironmentViewSet(viewsets.ModelViewSet):
    queryset = Environment.objects.all()
    serializer_class = EnvironmentSerializer

class TestRunViewSet(viewsets.ModelViewSet):
    queryset = TestRun.objects.all().order_by("-created_at")
    serializer_class = TestRunSerializer

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Start the run: set RUNNING and call executor (Celery)."""
        run = self.get_object()
        if run.status not in ("PENDING", "STOPPED", "ERROR"):
            return Response({"detail": "Run already started."}, status=status.HTTP_400_BAD_REQUEST)
        run.status = "RUNNING"
        run.started_at = timezone.now()
        run.save()
        # enqueue background execution (Celery)
        execute_test_run.delay(run.id)
        return Response({"detail": "Run started."})

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        run = self.get_object()
        run.status = "STOPPED"
        run.finished_at = timezone.now()
        run.save()
        return Response({"detail": "Run stopped."})

class TestExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TestExecution.objects.all().order_by("-started_at")
    serializer_class = TestExecutionSerializer


