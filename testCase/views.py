from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import viewsets, status, exceptions
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import Max
from django.conf import settings

from common.utils.email_service import send_notification_email, get_all_project_members_emails

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
        
        module = serializer.save(created_by=self.request.user)
        # [EMAIL] New Module
        recipients = get_all_project_members_emails(module.project)
        send_notification_email(
            subject=f"[{module.project.name}] New Module: {module.name}",
            recipients=recipients,
            template_path="emails/generic_notification.html",
            context={
                'title': "New Test Module",
                'message_body': f"A new test module '{module.name}' has been created.",
                'details': {
                    'Module': module.name,
                    'Description': module.description or "N/A",
                    'Created By': self.request.user.get_full_name()
                },
                'action_url': f"{settings.FRONTEND_URL}/projects/{module.project.id}/tests/modules"
            }
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
        module = serializer.save()
        # [EMAIL] Module Updated
        recipients = get_all_project_members_emails(module.project)
        send_notification_email(
            subject=f"[{module.project.name}] Module Updated: {module.name}",
            recipients=recipients,
            template_path="emails/generic_notification.html",
            context={
                'title': "Module Updated",
                'message_body': f"The test module '{module.name}' was updated.",
                'details': {'Module': module.name, 'Updated By': self.request.user.get_full_name()}
            }
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
        # return super().destroy(request, *args, **kwargs)
        # [EMAIL] Module Deleted
        project = module.project
        module_name = module.name
        recipients = get_all_project_members_emails(project)
        
        super().destroy(request, *args, **kwargs)

        send_notification_email(
            subject=f"[{project.name}] Module Deleted: {module_name}",
            recipients=recipients,
            template_path="emails/generic_notification.html",
            context={
                'title': "Module Deleted",
                'message_body': f"The test module '{module_name}' has been deleted.",
                'details': {'Deleted Module': module_name, 'Deleted By': request.user.get_full_name()}
            }
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


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

    def perform_create(self, serializer):
        suite = serializer.save(created_by=self.request.user)
        # Assuming TestSuite has a link to Project (e.g., via Module or direct FK)
        # Adjust 'suite.project' if your relationship is suite.module.project
        project = getattr(suite, 'project', None) or getattr(suite.module, 'project', None)
        
        if project:
            recipients = get_all_project_members_emails(project)
            send_notification_email(
                subject=f"[{project.name}] New Test Suite: {suite.name}",
                recipients=recipients,
                template_path="emails/generic_notification.html",
                context={
                    'title': "New Test Suite",
                    'message_body': f"Test Suite '{suite.name}' created by {self.request.user.get_full_name()}.",
                    'details': {'Suite': suite.name, 'Module': str(suite.module)},
                    'action_url': f"{settings.FRONTEND_URL}/projects/{project.id}/tests/suites/{suite.id}"
                }
            )

    @action(detail=True, methods=["post"])
    def add_case(self, request, pk=None):
        suite = self.get_object()
        data = request.data.copy()
        data["suite"] = suite.id
        serializer = TestCaseSerializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        case = serializer.save()

        # [EMAIL] Case Added to Suite
        project = getattr(suite, 'project', None) or getattr(suite.module, 'project', None)
        if project:
            recipients = get_all_project_members_emails(project)
            send_notification_email(
                subject=f"[{project.name}] Test Case Added to {suite.name}",
                recipients=recipients,
                template_path="emails/generic_notification.html",
                context={
                    'title': "Test Case Created",
                    'message_body': f"Test Case '{case.title}' was added to Suite '{suite.name}'.",
                    'details': {'Case': case.title, 'Suite': suite.name, 'Priority': case.priority},
                    'action_url': f"{settings.FRONTEND_URL}/projects/{project.id}/tests/cases/{case.id}"
                }
            )

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
        suite = serializer.save()

        # [EMAIL] Suite Update
        project = getattr(suite, 'project', None) or getattr(suite.module, 'project', None)
        if project:
            send_notification_email(
                subject=f"[{project.name}] Test Suite Updated: {suite.name}",
                recipients=get_all_project_members_emails(project),
                template_path="emails/generic_notification.html",
                context={'title': "Test Suite Updated", 'message_body': f"Suite '{suite.name}' was updated.", 'details': {'Suite': suite.name}}
            )
    
    def destroy(self, request, *args, **kwargs):
        suite = self.get_object()

        # block deletion if there are cases in this suite
        if suite.cases.exists():
            raise ValidationError({
                "detail": "Cannot delete suite while it still has test cases. "
                          "Delete or move those cases first."
            })
        # [EMAIL] Suite Deleted
        project = getattr(suite, 'project', None) or getattr(suite.module, 'project', None)
        if project:
            recipients = get_all_project_members_emails(project)
            send_notification_email(
                subject=f"[{project.name}] Test Suite Deleted: {suite.name}",
                recipients=recipients,
                template_path="emails/generic_notification.html",
                context={
                    'title': "Test Suite Deleted", 
                    'message_body': f"Test Suite '{suite.name}' was deleted by {request.user.get_full_name()}.",
                    'details': {'Deleted Suite': suite.name}
                }
            )
        return super().destroy(request, *args, **kwargs)


class TestCaseViewSet(viewsets.ModelViewSet):
    queryset = QaTestCase.objects.all()
    serializer_class = TestCaseSerializer

    def perform_create(self, serializer):
        case = serializer.save(created_by=self.request.user)
        # Determine Project from Module
        project = case.module.project if case.module else None
        
        if project:
            recipients = get_all_project_members_emails(project)
            send_notification_email(
                subject=f"[{project.name}] New Test Case: {case.title}",
                recipients=recipients,
                template_path="emails/generic_notification.html",
                context={
                    'title': "Test Case Created",
                    'message_body': f"A new test case '{case.title}' was created.",
                    'details': {
                        'Title': case.title,
                        'Module': case.module.name,
                        'Priority': case.priority
                    },
                    'action_url': f"{settings.FRONTEND_URL}/projects/{project.id}/tests/cases/{case.id}"
                }
            )

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
        case = serializer.save()
        # [EMAIL] Case Updated
        project = case.module.project if case.module else None
        if project:
            send_notification_email(
                subject=f"[{project.name}] Test Case Updated: {case.title}",
                recipients=get_all_project_members_emails(project),
                template_path="emails/generic_notification.html",
                context={
                    'title': "Test Case Updated",
                    'message_body': f"Test case '{case.title}' was updated.",
                    'details': {'Case': case.title, 'Updated By': self.request.user.get_full_name()},
                    'action_url': f"{settings.FRONTEND_URL}/projects/{project.id}/tests/cases/{case.id}"
                }
            )
    def perform_destroy(self, instance):
        project = instance.module.project if instance.module else None
        case_title = instance.title
        instance.delete()
        
        if project:
            send_notification_email(
                subject=f"[{project.name}] Test Case Deleted: {case_title}",
                recipients=get_all_project_members_emails(project),
                template_path="emails/generic_notification.html",
                context={
                    'title': "Test Case Deleted",
                    'message_body': f"Test case '{case_title}' was deleted by {self.request.user.get_full_name()}.",
                    'details': {'Deleted Case': case_title}
                }
            )





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
        template = serializer.save(created_by=self.request.user)
        # [EMAIL] New Template
        if template.project:
            send_notification_email(
                subject=f"[{template.project.name}] New Test Template: {template.name}",
                recipients=get_all_project_members_emails(template.project),
                template_path="emails/generic_notification.html",
                context={
                    'title': "New Test Template",
                    'message_body': f"A new test template '{template.name}' is available.",
                    'details': {'Template': template.name, 'Project': template.project.name}
                }
            )

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

    def perform_create(self, serializer):
        plan = serializer.save(created_by=self.request.user)
        # [EMAIL] New Test Plan
        if plan.project:
            send_notification_email(
                subject=f"[{plan.project.name}] New Test Plan: {plan.name}",
                recipients=get_all_project_members_emails(plan.project),
                template_path="emails/generic_notification.html",
                context={
                    'title': "New Test Plan",
                    'message_body': f"Test plan '{plan.name}' created.",
                    'details': {'Plan': plan.name, 'Description': plan.description},
                    'action_url': f"{settings.FRONTEND_URL}/projects/{plan.project.id}/tests/plans/{plan.id}"
                }
            )


class EnvironmentViewSet(viewsets.ModelViewSet):
    queryset = Environment.objects.all()
    serializer_class = EnvironmentSerializer

class TestRunViewSet(viewsets.ModelViewSet):
    queryset = TestRun.objects.all().order_by("-created_at")
    serializer_class = TestRunSerializer

    def perform_create(self, serializer):
        run = serializer.save(created_by=self.request.user)
        # [EMAIL] Test Run Created
        project = run.test_plan.project if run.test_plan else None
        if project:
            send_notification_email(
                subject=f"[{project.name}] Test Run Created: {run.name}",
                recipients=get_all_project_members_emails(project),
                template_path="emails/generic_notification.html",
                context={
                    'title': "Test Run Created",
                    'message_body': f"Test Run '{run.name}' is ready to start.",
                    'details': {'Run': run.name, 'Plan': run.test_plan.name},
                    'action_url': f"{settings.FRONTEND_URL}/projects/{project.id}/tests/runs/{run.id}"
                }
            )

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

         # [EMAIL] Test Run Started
        project = run.test_plan.project if run.test_plan else None
        if project:
            send_notification_email(
                subject=f"[{project.name}] Test Run Started: {run.name}",
                recipients=get_all_project_members_emails(project),
                template_path="emails/generic_notification.html",
                context={
                    'title': "Test Run Started",
                    'message_body': f"Execution for '{run.name}' has started.",
                    'details': {'Run': run.name, 'Started By': request.user.get_full_name()},
                    'action_url': f"{settings.FRONTEND_URL}/projects/{project.id}/tests/runs/{run.id}"
                }
            )

        return Response({"detail": "Run started."})

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        run = self.get_object()
        run.status = "STOPPED"
        run.finished_at = timezone.now()
        run.save()

         # [EMAIL] Test Run Stopped
        project = run.test_plan.project if run.test_plan else None
        if project:
            send_notification_email(
                subject=f"[{project.name}] Test Run Stopped: {run.name}",
                recipients=get_all_project_members_emails(project),
                template_path="emails/generic_notification.html",
                context={
                    'title': "Test Run Stopped",
                    'message_body': f"Execution for '{run.name}' was stopped manually.",
                    'details': {'Run': run.name, 'Stopped By': request.user.get_full_name()},
                    'action_url': f"{settings.FRONTEND_URL}/projects/{project.id}/tests/runs/{run.id}"
                }
            )
        return Response({"detail": "Run stopped."})

class TestExecutionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TestExecution.objects.all().order_by("-started_at")
    serializer_class = TestExecutionSerializer


