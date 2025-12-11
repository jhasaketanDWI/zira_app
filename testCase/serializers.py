from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from project.models import Project
from .models import (
    Module, TestSuite, QaTestCase, TestStep,
    Environment, TestPlan, TestRun, TestExecution,
    TestTemplate, TemplateStep,
)
from django.db import transaction
from django.db.models import Max 



class TemplateStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateStep
        fields = ["id", "order", "action", "data", "expected"]


class TestTemplateSerializer(serializers.ModelSerializer):
    template_steps = TemplateStepSerializer(many=True, required=False)

    class Meta:
        model = TestTemplate
        fields = [
            "id",
            "project",
            "name",
            "description",
            "is_active",
            "template_steps",
        ]

    def create(self, validated_data):
        steps_data = validated_data.pop("template_steps", [])
        template = TestTemplate.objects.create(**validated_data)

        for i, step in enumerate(steps_data, start=1):
            TemplateStep.objects.create(
                template=template,
                order=step.get("order", i),
                action=step.get("action", ""),
                data=step.get("data", ""),
                expected=step.get("expected", ""),
            )
        return template
    

class TestStepSerializer(serializers.ModelSerializer):
    """Full serializer for standalone step CRUD endpoints."""
    case = serializers.PrimaryKeyRelatedField(queryset=QaTestCase.objects.all())

    class Meta:
        model = TestStep
        fields = ["id", "case", "order", "action", "data", "expected"]

class NestedTestStepSerializer(serializers.ModelSerializer):
    """Used only when nested under a TestCase (no `case` field here)."""
    class Meta:
        model = TestStep
        fields = ["id", "order", "action", "data", "expected"]

class TestCaseSerializer(serializers.ModelSerializer):
    steps = NestedTestStepSerializer(many=True, required=False)
    template = serializers.PrimaryKeyRelatedField(
        queryset=TestTemplate.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = QaTestCase
        fields = [
            "id","suite","title","preconditions",
            "expected_result","priority","natural_language",
            "status","labels","severity","module","template","steps",
        ]

    def create(self, validated_data):
        steps_data = validated_data.pop("steps", [])
        template = validated_data.pop("template", None)

        # create the test case itself, with template reference (optional)
        case = QaTestCase.objects.create(template=template, **validated_data)

        # If explicit steps are provided, they are the final truth
        if steps_data:
            for i, s in enumerate(steps_data, start=1):
                TestStep.objects.create(
                    case=case,
                    order=s.get("order", i),
                    action=s.get("action", ""),
                    data=s.get("data", ""),
                    expected=s.get("expected", ""),
                )

        # Else if no explicit steps but template present, clone from template
        elif template:
            for t_step in template.template_steps.all():
                TestStep.objects.create(
                    case=case,
                    order=t_step.order,
                    action=t_step.action,
                    data=t_step.data,
                    expected=t_step.expected,
                )

        # Else: no steps; user can add later via /steps/ endpoint
        return case

    def update(self, instance, validated_data):
        steps_data = validated_data.pop("steps", None)
        template = validated_data.pop("template", None)

        # Update scalar fields
        for attr, val in validated_data.items():
            setattr(instance, attr, val)

        # You probably *do* want to allow updating template reference
        if template is not None:
            instance.template = template

        instance.save()

        # If 'steps' key is present in the payload (even empty list),
        # we treat it as final and fully replace existing steps.
        if steps_data is not None:
            instance.steps.all().delete()
            for i, s in enumerate(steps_data, start=1):
                TestStep.objects.create(
                    case=instance,
                    order=s.get("order", i),
                    action=s.get("action", ""),
                    data=s.get("data", ""),
                    expected=s.get("expected", ""),
                )

        return instance
    
class SimpleTestCaseSerializer(serializers.ModelSerializer):
    """Only id + name (title) for test cases."""
    class Meta:
        model = QaTestCase
        fields = ["id", "title"]




class TestSuiteSerializer(serializers.ModelSerializer):
    cases = TestCaseSerializer(many=True, read_only=True)

    class Meta:
        model = TestSuite
        fields = ["id", "module", "name", "description", "suite_type", "cases"]

class RecursiveModuleSerializer(serializers.Serializer):
    def to_representation(self, value):
        return ModuleSerializer(value, context=self.context).data

class ModuleSerializer(serializers.ModelSerializer):
    children = RecursiveModuleSerializer(many=True, read_only=True)
    testcases = TestCaseSerializer(many=True, read_only=True)
    parent = serializers.PrimaryKeyRelatedField(queryset=Module.objects.all(), required=False, allow_null=True)
    project = serializers.PrimaryKeyRelatedField(queryset=Project.objects.all())

    class Meta:
        model = Module
        fields = ["id", "project", "parent", "name", "description", "created_by", "created_at", "testcases", "children"]
        read_only_fields = ["created_by", "created_at"]
    
    def validate(self, data):
        """
        Check that if a parent module is provided, 
        it belongs to the same project specified for the new module.
        """
        parent_module = data.get("parent")
        new_module_project = data.get("project")

        if parent_module and new_module_project:
            # Check the parent module's project against the new module's project
            # 'parent_module' is an instance of Module model at this point,
            # and 'new_module_project' is an instance of RootProject model.
            
            # parent_module.project is a RootProject instance (from the FK relationship)
            if parent_module.project != new_module_project:
                raise ValidationError({
                    "parent": "The parent module must belong to the same project specified for the new module."
                })
        
        return data

    def create(self, validated_data):
        request = self.context.get("request")
        if request and not validated_data.get("created_by"):
            validated_data["created_by"] = request.user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)

class SimpleModuleSerializer(serializers.ModelSerializer):
    """
    Recursive module tree: id + name + children
    (no test cases).
    """
    children = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = ["id", "name", "children"]

    def get_children(self, obj):
        # Recursively serialize children
        queryset = obj.children.all()
        return SimpleModuleSerializer(queryset, many=True).data

class SimpleModuleWithCasesSerializer(serializers.ModelSerializer):
    """
    Recursive module tree with test cases:
    - module: id, name
    - children: same
    - testcases: id, title only
    """
    children = serializers.SerializerMethodField()
    testcases = SimpleTestCaseSerializer(many=True, read_only=True)

    class Meta:
        model = Module
        fields = ["id", "name", "children", "testcases"]

    def get_children(self, obj):
        queryset = obj.children.all()
        return SimpleModuleWithCasesSerializer(queryset, many=True).data



class EnvironmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Environment
        fields = ["id", "project", "name", "url", "details"]

class TestPlanSerializer(serializers.ModelSerializer):
    suites = serializers.PrimaryKeyRelatedField(many=True, queryset=TestSuite.objects.all(), required=False)

    class Meta:
        model = TestPlan
        fields = ["id", "project", "name", "description", "suites"]

class TestExecutionSerializer(serializers.ModelSerializer):
    case = serializers.PrimaryKeyRelatedField(queryset=QaTestCase.objects.all())
    class Meta:
        model = TestExecution
        fields = ["id", "run", "case", "status", "started_at", "finished_at", "log", "artifacts", "executed_by"]

class TestRunSerializer(serializers.ModelSerializer):
    executions = TestExecutionSerializer(many=True, read_only=True)
    suites = serializers.PrimaryKeyRelatedField(many=True, queryset=TestSuite.objects.all(), required=False)

    class Meta:
        model = TestRun
        fields = [
            "id","project","name","plan","suites","environment","created_by",
            "created_at","started_at","finished_at","status","meta","executions"
        ]

    def create(self, validated_data):
        suites = validated_data.pop("suites", [])
        with transaction.atomic():
            run = TestRun.objects.create(**validated_data)
            # populate suites either from plan or explicit list
            if validated_data.get("plan"):
                for s in run.plan.suites.all():
                    run.suites.add(s)
            if suites:
                for s in suites:
                    run.suites.add(s)

            # Create TestExecution rows for all cases (use correct model)
            case_qs = QaTestCase.objects.filter(suite__in=run.suites.all()).distinct()
            for case in case_qs:
                TestExecution.objects.create(run=run, case=case, status="PENDING")
        return run



