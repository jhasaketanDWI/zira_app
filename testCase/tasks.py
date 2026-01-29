# qa/tasks.py
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from jira_app.common.utils.email_service import get_stakeholders_emails, send_notification_email
from .models import TestRun, TestExecution
import time
import traceback

@shared_task(bind=True)
def execute_test_run(self, run_id):
    """
    Celery worker task to execute a TestRun.
    This is a scaffold: replace the inner loop with your automation invocation,
    e.g. call a Selenium runner, Playwright script, or call an external test service.
    """
    try:
        run = TestRun.objects.get(pk=run_id)
        run.status = "RUNNING"
        run.started_at = timezone.now()
        run.save()

        executions = run.executions.select_related("case").all()
        # For each case, run steps (synchronously here). Replace with real runner calls.
        for exec_obj in executions:
            exec_obj.status = "RUNNING"
            exec_obj.started_at = timezone.now()
            exec_obj.save()

            try:
                # === Replace below with actual automation invocation ===
                # Example: call external runner like:
                # result = my_runner.run_case(exec_obj.case, environment=run.environment, meta=run.meta)
                # expected result dict: {"status": "PASSED"/"FAILED", "log": "...", "artifacts": {...}}
                time.sleep(1)  # placeholder simulating runtime
                # simulate pass/fail logic here:
                result = {"status": "PASSED", "log": f"Executed {exec_obj.case.title}", "artifacts": {}}

                exec_obj.status = result.get("status", "FAILED")
                exec_obj.log = result.get("log", "")
                exec_obj.artifacts = result.get("artifacts", {})
            except Exception as e:
                exec_obj.status = "ERROR"
                exec_obj.log = f"Exception: {traceback.format_exc()}"
            exec_obj.finished_at = timezone.now()
            exec_obj.save()

        # finalize run status
        overall_failed = executions.filter(status__in=["FAILED", "ERROR"]).exists()
        run.status = "FAILED" if overall_failed else "PASSED"
        run.finished_at = timezone.now()
        run.save()
        try:
            recipients = get_stakeholders_emails(run.project)
            
            # Statistics
            total = executions.count()
            passed = executions.filter(status="PASSED").count()
            failed = executions.filter(status__in=["FAILED", "ERROR"]).count()
            
            send_notification_email(
                subject=f"[{run.project.name}] Test Run {run.status}: {run.name}",
                recipients=recipients,
                template_path="emails/notification.html",
                context={
                    'title': f"Test Run {run.status.title()}",
                    'message_body': f"Automated test run '{run.name}' has finished execution.",
                    'details': {
                        'Status': run.status,
                        'Total Cases': total,
                        'Passed': passed,
                        'Failed': failed,
                        'Duration': f"{(run.finished_at - run.started_at).seconds}s" if run.started_at else "N/A"
                    },
                    'action_url': f"{settings.FRONTEND_URL}/projects/{run.project.id}/test-runs/{run.id}"
                }
            )
        except Exception as e:
            print(f"Failed to send test run email: {e}")
        return {"run_id": run_id, "status": run.status}
    except Exception as exc:
        # mark run as error
        try:
            run = TestRun.objects.get(pk=run_id)
            run.status = "ERROR"
            run.finished_at = timezone.now()
            run.save()
        except:
            pass
        raise exc
