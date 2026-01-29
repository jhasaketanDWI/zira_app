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

    def __str__(self):
        return "Current Pricing Configuration"

class Subscription(AuditBaseModel):
    BILLING_CYCLE_CHOICES = [
        ('MONTHLY', 'Monthly'),
        ('YEARLY', 'Yearly'),
        ('FREE_TRIAL', 'Free Trial')
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    selected_users = models.IntegerField(default=5)
    selected_storage_gb = models.IntegerField(default=10)
    selected_testcases = models.IntegerField(default=500)
    
    billing_cycle = models.CharField(max_length=20, choices=BILLING_CYCLE_CHOICES, default='MONTHLY')
    
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField()
    
    is_active = models.BooleanField(default=True)
    price_at_activation = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    def calculate_cost(self):
        """
        Calculates the monthly/yearly cost based on current PricingConfig.
        Uses Decimal for financial precision.
        """
        config = PricingConfig.objects.first()
        # Fallback defaults if no config exists (Safety)
        if not config: 
            return Decimal('0.00')

        # Convert inputs to Decimal
        user_cost = Decimal(self.selected_users) * config.price_per_user
        storage_cost = Decimal(self.selected_storage_gb) * config.price_per_gb
        
        # Testcases are sold in units (e.g., per 500)
        # Avoid float division: (Total / Step) * Price
        units = Decimal(self.selected_testcases) / Decimal(config.testcase_unit_step)
        testcase_cost = units * config.price_per_testcase_unit

        monthly_total = user_cost + storage_cost + testcase_cost

        if self.billing_cycle == 'YEARLY':
            # 1 Month discount for yearly
            return (monthly_total * Decimal('11')).quantize(Decimal("0.01"))
        
        return monthly_total.quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        # Ensure start_date is a date object
        if isinstance(self.start_date, datetime.datetime):
            self.start_date = self.start_date.date()
            
        # Auto-set end_date if it's a new record
        if not self.pk:
            if self.billing_cycle == 'FREE_TRIAL':
                self.end_date = self.start_date + relativedelta(months=4)
            elif self.billing_cycle == 'YEARLY':
                self.end_date = self.start_date + relativedelta(years=1)
            else:
                self.end_date = self.start_date + relativedelta(months=1)
                
        # Snapshot the price if activating
        if self.is_active and not self.price_at_activation:
            self.price_at_activation = self.calculate_cost()
            
        super().save(*args, **kwargs)

class Invoice(AuditBaseModel):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    period_start = models.DateField()
    period_end = models.DateField()
    is_paid = models.BooleanField(default=False)
    # Optional: Add transaction_id for future payment gateway integration
    transaction_id = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"Invoice #{self.id} - {self.amount}"