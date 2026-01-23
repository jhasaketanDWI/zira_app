import json
from django.http import FileResponse
from rest_framework.response import Response
from django.shortcuts import render
from rest_framework.decorators import action
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework import viewsets, status, exceptions
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Max


from .services import get_ai_response, parse_testcase_excel, extract_json_from_ai, generate_testcase_excel
from common.permissions import RBACPermission
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
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'create': 'testCase.can_create_module',
        'update': 'testCase.can_edit_module',  
        'partial_update': 'testCase.can_edit_module',
        'destroy': 'testCase.can_delete_module',
        'list': 'testCase.can_view_all_module', 
        'retrieve': 'testCase.can_view_all_module',

        # Custom Action
        'update_parent':'testCase.can_edit_module',
        'tree_with_cases':'testCase.can_view_all_module',
        'tree':'testCase.can_view_all_module'
    }

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
        
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user
        )
    
    def perform_update(self, serializer):
        allowed_fields = {"name", "description", "parent"}

        # Keys the client is trying to update
        incoming_fields = set(serializer.validated_data.keys())

        disallowed = incoming_fields - allowed_fields
        if disallowed:
            raise ValidationError(
                {"detail": f"You cannot update these fields: {', '.join(disallowed)}"}
            )
        serializer.save(updated_by=self.request.user)

    @action(detail=True, methods=["patch"], url_path="move")
    def update_parent(self, request, pk=None):
        """
        Update ONLY the parent module of a module.
        """
        module = self.get_object()
        parent_id = request.data.get("parent")

        if parent_id is None:
            raise ValidationError({"parent": "Parent module ID is required."})

        if parent_id == module.id:
            raise ValidationError({"parent": "Module cannot be parent of itself."})

        try:
            parent = Module.objects.get(id=parent_id)
        except Module.DoesNotExist:
            raise ValidationError({"parent": "Invalid parent module ID."})

        # Ensure same project
        if parent.project_id != module.project_id:
            raise ValidationError({
                "parent": "Parent module must belong to the same project."
            })

        module.parent = parent
        module.save()

        return Response(
            {"message": "Parent module updated successfully"},
            status=status.HTTP_200_OK
        ) 
       
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
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'create': 'testCase.can_create_suite',
        'update': 'testCase.can_edit_suite',  
        'partial_update': 'testCase.can_edit_suite',
        'destroy': 'testCase.can_delete_suite',
        'list': 'testCase.can_view_all_suites',
        'retrieve': 'testCase.can_view_all_suites',

        # Custom Action
        'add_case':'testCase.can_add_testcases'
    }

    def get_queryset(self):
        project_id = self.request.query_params.get("project")
        if not project_id:
            raise ValidationError({"project": "project query parameter is required"})
        return TestSuite.objects.filter(project_id=project_id)
    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

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
            "name","description","case_ids",
            
        }
        incoming = set(serializer.validated_data.keys())
        disallowed = incoming - allowed_fields

        if disallowed:
            raise ValidationError({
                "detail": f"You cannot update these fields: {', '.join(disallowed)}"
            })

        instance = serializer.save()
    
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
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'create': 'testCase.can_create_testcase',
        'update': 'testCase.can_edit_testcases',  
        'partial_update': 'testCase.can_edit_testcases',
        'destroy': 'testCase.can_delete_testcases',
        'list': 'testCase.can_view_all_testcases',
        'retrieve': 'testCase.can_view_all_testcases',

        # Custom Action
        'update_module':'testCase.can_edit_parent_module',
        'import_excel':'testCase.can_create_testcase',
        'add_steps':'testCase.can_edit_testcase'
    }

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
        
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
    
    @action(detail=True, methods=["patch"], url_path="move")
    def update_module(self, request, pk=None):
        """
        Update ONLY the module of a test case.
        """
        testcase = self.get_object()
        module_id = request.data.get("module")

        if not module_id:
            raise ValidationError({"module": "Module ID is required."})

        try:
            module = Module.objects.get(id=module_id)
        except Module.DoesNotExist:
            raise ValidationError({"module": "Invalid module ID."})

        testcase.module = module
        testcase.save()

        return Response(
            {"message": "Test case successfully moved to"},
            status=status.HTTP_200_OK
        )
    
    @action(detail=False,methods=["post"],url_path="import_excel",parser_classes=[MultiPartParser, FormParser],)
    def import_excel(self, request):
        """
        Import test cases from Excel using TestCaseSerializer
        """
        excel = request.FILES.get("file")
        module_id = request.data.get("module")
        template_id = request.data.get("template")

        if not excel:
            raise ValidationError(
                {"file": "Excel based testcase file is required"}
            )

        parsed = parse_testcase_excel(excel)
        created = []

        for data in parsed.values():
            payload = {
                "module": module_id,
                "template": template_id,
                **data["meta"],
                "steps": data["steps"],
            }

            serializer = TestCaseSerializer(
                data=payload,
                context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            created.append(serializer.save(created_by=self.request.user))

        return Response(
            {
                "created_count": len(created),
                "testcases": TestCaseSerializer(created, many=True).data,
            },
            status=status.HTTP_201_CREATED
        )



class TestStepViewSet(viewsets.ModelViewSet):
    """
    CRUD API for TestStep.
    Base URL (after router): /testcase/steps/
    """
    queryset = TestStep.objects.all().order_by("order", "id")
    serializer_class = TestStepSerializer
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'create': 'testCase.can_create_test_steps',
        'update': 'testCase.can_edit_test_steps',  
        'partial_update': 'testCase.can_edit_test_steps',
        'destroy': 'testCase.can_delete_test_steps',
        'list': 'testCase.can_view_all_test_steps',
        'retrieve': 'testCase.can_view_all_test_steps',
    }

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
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'create': 'testCase.can_create_testTemplate',
        'update': 'testCase.can_edit_testTemplate',  
        'partial_update': 'testCase.can_edit_testTemplate',
        'destroy': 'testCase.can_delete_testTemplate',
        'list': 'testCase.can_view_all_testTemplate',
        'retrieve': 'testCase.can_view_all_testTemplate',
    }

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
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'create': 'testCase.can_create_template_steps',
        'update': 'testCase.can_edit_template_steps',  
        'partial_update': 'testCase.can_edit_template_steps',
        'destroy': 'testCase.can_delete_template_steps',
        'list': 'testCase.can_view_all_template_steps',
        'retrieve': 'testCase.can_view_all_template_steps',
    }

    def get_queryset(self):
        qs = super().get_queryset()
        template_id = self.request.query_params.get("template")
        if template_id:
            qs = qs.filter(template_id=template_id)
        return qs


class TestPlanViewSet(viewsets.ModelViewSet):
    queryset = TestPlan.objects.all()
    serializer_class = TestPlanSerializer
    permission_classes = [IsAuthenticated]

class EnvironmentViewSet(viewsets.ModelViewSet):
    queryset = Environment.objects.all()
    serializer_class = EnvironmentSerializer
    permission_classes = [IsAuthenticated]

class TestRunViewSet(viewsets.ModelViewSet):
    queryset = TestRun.objects.all().order_by("-created_at")
    serializer_class = TestRunSerializer
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]




class AITestScriptViewSet(viewsets.ModelViewSet):
    """
    API endpoint for interacting with the DeepSeek LLM.
    Accepts a 'prompt' (text) and an optional 'file' upload.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = (MultiPartParser, FormParser)

    def create(self, request, *args, **kwargs):
        # Get the text prompt from the request data
        user_prompt = request.data.get('prompt')
        # get the selected tool and language
        tool = request.data.get('tool')
        language = request.data.get('language')

        if not tool:
            return Response(
                {"error": "tool is required (e.g. selenium, playwright, cypress)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not language:
            return Response(
                {"error": "language is required (e.g. python, java, javascript)"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the uploaded file from the request
        uploaded_file = request.FILES.get('file')

        # Validate that we have at least a prompt
        if not user_prompt:
            return Response(
                {"error": "A 'prompt' field is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        file_content = ""
        if uploaded_file:
            # Check file size to prevent very large uploads (e.g., 10MB limit)
            if uploaded_file.size > 10 * 1024 * 1024:
                return Response(
                    {"error": "File size exceeds the 10MB limit."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Read the file content. Using decode with error handling is robust.
            try:
                file_content = uploaded_file.read().decode('utf-8')
            except UnicodeDecodeError:
                return Response(
                    {"error": "Could not decode the file. Please ensure it is a valid text file (e.g., UTF-8)."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        structured_prompt = f"""
        Tool: {tool.capitalize()}
        Language: {language.capitalize()}
        Task: {user_prompt}

        Generate a complete, runnable {tool.capitalize()} test script in {language.capitalize()} that automates the task above.
        Include realistic locators, assertions, and setup/teardown where appropriate.
        """

        # Call our service function to get the AI response
        ai_response = get_ai_response(user_prompt=structured_prompt, file_content=file_content)

        # Check if the service function returned an error message
        if isinstance(ai_response, dict):
            if "error" in ai_response:
                return Response(ai_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 
            return Response(ai_response, status=status.HTTP_200_OK)

        # Return the successful response from the AI
        return Response(
            {"response": ai_response},
            status=status.HTTP_200_OK
        )
    
    @action(detail=False,methods=["post"],url_path="generate_excel",parser_classes=[JSONParser, MultiPartParser, FormParser],)
    def generate_testcase(self, request):
        feature = request.data.get("feature")
        minimum_case = request.data.get("min_case")
        if not feature:
            return Response(
                {"error": "feature description is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        prompt = f"""
        You are a Senior QA Engineer.

        STRICT RULES (MANDATORY):
        1. Generate AT LEAST {minimum_case} DISTINCT manual test cases.
        2. Each test case must cover a DIFFERENT scenario.
        3. Cover: positive, negative, edge, validation, security cases.
        4. Return ONLY valid JSON. No markdown. No explanation.

        Allowed Labels (STRICT):
        - FUNCTIONAL
        - SMOKE
        - REGRESSION
        - PERFORMANCE
        - INTEGRATION

        Rules:
        - Use ONLY ONE label per test case
        - Do NOT invent labels
        - Do NOT combine labels (no commas, no pipes)
        JSON FORMAT:

        [
        {{
            "title": "Descriptive test case title",
            "preconditions": "Any setup",
            "priority": "LOW | MEDIUM | HIGH",
            "severity": "MINOR | MAJOR | CRITICAL",
            "labels": "FUNCTIONAL",
            "expected_result": "Expected outcome",
            "steps": [
            {{
                "order": 1,
                "action": "",
                "data": "Input",
                "expected": ""
            }}
            ]
        }}
        ]

        Feature / Module:
        {feature}

        REMEMBER:
        - Minimum {minimum_case} test cases is REQUIRED.
        """

        ai_result = get_ai_response(prompt)

        #  Normalize AI response
        if isinstance(ai_result, str):
            return Response(
                {"error": "AI service error", "detail": ai_result},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        if "error" in ai_result:
            return Response(ai_result, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        ai_message = ai_result.get("ai_message")
        if not ai_message:
            return Response(
                {"error": "AI response missing ai_message"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        try:
            testcases = extract_json_from_ai(ai_message)
        except Exception:
            return Response(
                {
                    "error": "AI returned invalid JSON",
                    "raw_response": ai_message[:1500]
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        excel_path = generate_testcase_excel(testcases)

        return FileResponse(
            open(excel_path, "rb"),
            as_attachment=True,
            filename="ai_generated_testcases.xlsx"
        )





# For development use 
def ai_chat_page(request):
    """
    Renders the main chat interface page.
    """
    return render(request, 'testcase.html')