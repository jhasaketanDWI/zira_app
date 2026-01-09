from django.db import models
from common.models import AuditBaseModel
from django.conf import settings
from django.utils import timezone
from dateutil.relativedelta import relativedelta
import datetime
from decimal import Decimal 

class PricingConfig(AuditBaseModel):
    """
    Admin-configurable pricing and limits.
    """
    price_per_user = models.DecimalField(max_digits=6, decimal_places=2, default=1.00)
    price_per_gb = models.DecimalField(max_digits=6, decimal_places=2, default=1.00)
    price_per_testcase_unit = models.DecimalField(max_digits=6, decimal_places=2, default=1.00) 
    
    # Logic Constraints
    min_users = models.IntegerField(default=5)
    min_storage_base = models.IntegerField(default=10) # 10GB base for 5 users
    storage_per_user_step = models.IntegerField(default=2) # +2GB per extra user
    testcase_unit_step = models.IntegerField(default=500) # Steps of 500

    class Meta:
        verbose_name = "Pricing Configuration"
        # Only admins should touch this

    def __str__(self):
        return "Current Pricing Configuration"

class Subscription(AuditBaseModel):
    BILLING_CYCLE_CHOICES = [
        ('MONTHLY', 'Monthly'),
        ('YEARLY', 'Yearly'), # 11 months price for 12 months
        ('FREE_TRIAL', 'Lakadi Free Trial'), # 4 Months fixed
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    
    # Resource Sliders
    selected_users = models.IntegerField(default=0)
    selected_storage_gb = models.IntegerField(default=0)
    selected_testcases = models.IntegerField(default=0)

    # Billing Info
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLE_CHOICES, default='MONTHLY')
    price_at_activation = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        # UPDATED PERMISSIONS HERE
        permissions = [
            ("view_subscription_plan", "Can view current subscription details"),
            ("manage_subscription_plan", "Can upgrade/downgrade resources (Owner/Scrum Master)"),
            ("pay_invoice", "Can process billing payments"),
        ]

    def calculate_cost(self):
        """Dynamic cost calculation based on resources."""
        config = PricingConfig.objects.first()
        if not config:
            return 0.00
        
        if self.billing_cycle == 'FREE_TRIAL':
            return 0.00

        user_cost = self.selected_users * config.price_per_user
        storage_cost = self.selected_storage_gb * config.price_per_gb
        
        # Testcases are sold in blocks (e.g., blocks of 500)
        testcase_units = self.selected_testcases / config.testcase_unit_step
        testcase_cost = Decimal(testcase_units) * config.price_per_testcase_unit

        monthly_total = user_cost + storage_cost + testcase_cost

        if self.billing_cycle == 'YEARLY':
            return monthly_total * 11 # 1 month free
        
        return monthly_total

    def save(self, *args, **kwargs):
        if isinstance(self.start_date, datetime.datetime):
            self.start_date = self.start_date.date()
        # Auto-set dates if new
        if not self.id:
            if self.billing_cycle == 'FREE_TRIAL':
                self.end_date = self.start_date + relativedelta(months=4)
            elif self.billing_cycle == 'YEARLY':
                self.end_date = self.start_date + relativedelta(years=1)
            else:
                self.end_date = self.start_date + relativedelta(months=1)
        super().save(*args, **kwargs)

class Invoice(AuditBaseModel):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    period_start = models.DateField()
    period_end = models.DateField()
    paid = models.BooleanField(default=False)
    external_ref = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        permissions = [
            ("view_invoices", "Can view billing history"),
        ]