from django.db import models
from common.models import AuditBaseModel
from django.conf import settings


class SubscriptionPlan(AuditBaseModel):
    name = models.CharField(max_length=100)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2)
    user_limit = models.IntegerField()
    testcase_limit = models.IntegerField()
    project_limit = models.IntegerField()
    features = models.JSONField(default=dict)

    def __str__(self):
        return self.name


class Subscription(AuditBaseModel):
    class Meta:
        permissions = [
            ("can_manage_subscription", "User can change the project's subscription plan"),
            ("can_edit_billing_info", "User can update payment methods and billing addresses"),
        ]
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.PROTECT)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.owner.email}'s {self.plan.name} Plan"


class Invoice(AuditBaseModel):
    class Meta:
        permissions = [
            ("can_view_all_invoices", "User can access the entire billing and invoice history"),
        ]
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    period_start = models.DateField()
    period_end = models.DateField()
    paid = models.BooleanField(default=False)
    external_ref = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Invoice {self.id} for {self.subscription.owner.email}"

