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

class DiscountCode(AuditBaseModel):
    """
    Discount coupons that can be applied to Subscriptions.
    Adapted from user request to fit AuditBaseModel.
    """
    DISCOUNT_TYPES = [
        ('PERCENT', 'Percentage'),
        ('FIXED', 'Fixed Amount')
    ]

    code = models.CharField(max_length=20, unique=True)
    discount_type = models.CharField(max_length=10, choices=DISCOUNT_TYPES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    expiry_date = models.DateTimeField()
    usage_limit = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)
    

    def is_valid(self):
        """Check if the discount code is still valid."""
        return self.used_count < self.usage_limit and self.expiry_date > timezone.now()

    def use_code(self):
        """Increment the usage count when applied successfully."""
        self.used_count += 1
        self.save()

    def __str__(self):
        return f"{self.code} ({self.get_discount_type_display()} - {self.discount_value})"

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

    applied_discount = models.ForeignKey(DiscountCode, on_delete=models.SET_NULL, null=True, blank=True)

    def calculate_cost(self):
        """
        Calculates cost based on config AND applied discount.
        """
        config = PricingConfig.objects.first()
        if not config: 
            return Decimal('0.00')

        # 1. Base Cost Calculation
        user_cost = Decimal(self.selected_users) * config.price_per_user
        storage_cost = Decimal(self.selected_storage_gb) * config.price_per_gb
        
        units = Decimal(self.selected_testcases) / Decimal(config.testcase_unit_step)
        testcase_cost = units * config.price_per_testcase_unit

        subtotal = user_cost + storage_cost + testcase_cost

        if self.billing_cycle == 'YEARLY':
            subtotal = subtotal * Decimal('11') # 1 month free discount
        
        # 2. Apply Discount Code Logic
        if self.applied_discount and self.applied_discount.is_valid():
            if self.applied_discount.discount_type == 'PERCENT':
                discount_amount = subtotal * (self.applied_discount.discount_value / Decimal('100'))
            else: # FIXED
                discount_amount = self.applied_discount.discount_value
            
            subtotal = subtotal - discount_amount
        
        # Ensure non-negative
        return max(Decimal('0.00'), subtotal.quantize(Decimal("0.01")))

    def save(self, *args, **kwargs):
        if isinstance(self.start_date, datetime.datetime):
            self.start_date = self.start_date.date()
            
        if not self.pk:
            if self.billing_cycle == 'FREE_TRIAL':
                self.end_date = self.start_date + relativedelta(months=4)
            elif self.billing_cycle == 'YEARLY':
                self.end_date = self.start_date + relativedelta(years=1)
            else:
                self.end_date = self.start_date + relativedelta(months=1)
                
        if self.is_active and not self.price_at_activation:
            self.price_at_activation = self.calculate_cost()
            
        super().save(*args, **kwargs)

class Invoice(AuditBaseModel):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name='invoices')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    period_start = models.DateField()
    period_end = models.DateField()
    is_paid = models.BooleanField(default=False)
    transaction_id = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"Invoice #{self.id} - {self.amount}"

class Payment(AuditBaseModel):
    """
    Records a payment attempt for a specific Invoice.
    Adapted from user request.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('SUCCESS', 'Success'),
        ('FAILED', 'Failed')
    ]

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    transaction_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    payment_id = models.AutoField(primary_key=True)

    
   
    def __str__(self):
        return f"Payment {self.id} - {self.payment_status}"