from rest_framework import serializers
from .models import Subscription, PricingConfig, Invoice, DiscountCode, Payment
from decimal import Decimal

class DiscountCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiscountCode
        fields = ['id', 'code', 'discount_type', 'discount_value', 'expiry_date', 'usage_limit', 'used_count']
        read_only_fields = ['used_count']

class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ['id', 'invoice', 'amount_paid', 'payment_status', 'transaction_id', 'created_at']
        read_only_fields = ['created_at']

class SubscriptionSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    total_price = serializers.SerializerMethodField()
    formatted_status = serializers.SerializerMethodField()

    discount_code_str = serializers.CharField(write_only=True, required=False, allow_blank=True)
    applied_discount = DiscountCodeSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id', 'owner', 'selected_users', 'selected_storage_gb', 
            'selected_testcases', 'billing_cycle', 'start_date', 
            'end_date', 'is_active', 'total_price', 'formatted_status','discount_code_str', 'applied_discount'
        ]
        read_only_fields = ['start_date', 'end_date', 'is_active', 'price_at_activation']

    def get_total_price(self, obj):
        return obj.calculate_cost()
    # def get_formatted_status(self, obj):
    #     if not obj.is_active: 
    #         return "Pending Payment"  # Or "Inactive"
    #     if obj.billing_cycle == 'FREE_TRIAL':
    #         return "Free Trial"
    #     return "Active Premium"
    def get_formatted_status(self, obj):
        if not obj.is_active: return "Inactive"
        return "Free Trial" if obj.billing_cycle == 'FREE_TRIAL' else "Active Premium"

    def validate(self, data):
        users = data.get('selected_users', 0)
        storage = data.get('selected_storage_gb', 0)
        testcases = data.get('selected_testcases', 0)
        
        # Dynamic Validation based on Admin Config
        config = PricingConfig.objects.first()
        if not config:
            raise serializers.ValidationError("Pricing configuration is missing. Contact Admin.")

        # 1. User Limits
        if users < config.min_users:
             raise serializers.ValidationError({"selected_users": f"Minimum {config.min_users} users required."})

        # 2. Storage Logic (Base + Extra per user)
        # Calculate expected minimum storage based on users
        # e.g. 5 users = 10GB base. 6 users = 10 + 2 = 12GB.
        extra_users = max(0, users - config.min_users)
        min_storage = config.min_storage_base + (extra_users * config.storage_per_user_step)
        
        if storage < min_storage:
             raise serializers.ValidationError({
                 "selected_storage_gb": f"For {users} users, storage cannot be less than {min_storage}GB."
             })

        # 3. Testcase Logic (Steps)
        if testcases < config.testcase_unit_step:
             raise serializers.ValidationError({"selected_testcases": f"Minimum testcases is {config.testcase_unit_step}."})
        
        if testcases % config.testcase_unit_step != 0:
             raise serializers.ValidationError({"selected_testcases": f"Testcases must increase by {config.testcase_unit_step}."})

        return data
    def create(self, validated_data):
        code_str = validated_data.pop('discount_code_str', None)
        discount = None
        if code_str:
            discount = DiscountCode.objects.get(code=code_str)
            # We don't increment usage here, we do it upon Payment success usually, 
            # or here if it's applied immediately to a subscription logic.
            # For simplicity, we'll increment when the Subscription is saved active.
            
        instance = super().create(validated_data)
        if discount:
            instance.applied_discount = discount
            instance.save()
        return instance

    def update(self, instance, validated_data):
        code_str = validated_data.pop('discount_code_str', None)
        instance = super().update(instance, validated_data)
        
        if code_str:
            discount = DiscountCode.objects.get(code=code_str)
            instance.applied_discount = discount
            instance.save()
        return instance

class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = '__all__'


class PricingConfigSerializer(serializers.ModelSerializer):
    """
    Allows the Admin Frontend to fetch and update the base prices.
    """
    class Meta:
        model = PricingConfig
        fields = [
            'id', 'price_per_user', 'price_per_gb', 'price_per_testcase_unit',
            'min_users', 'min_storage_base', 'storage_per_user_step', 'testcase_unit_step', 
            'updated_at'
        ]
        read_only_fields = ['id', 'updated_at']

class BillingReportSerializer(serializers.Serializer):
    """
    Serializer to format data for Frontend Charts
    """
    month = serializers.CharField()
    total_spend = serializers.DecimalField(max_digits=12, decimal_places=2)
    invoice_count = serializers.IntegerField()

class SubscriptionUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = ['selected_users', 'selected_storage_gb', 'selected_testcases', 'billing_cycle']

    def validate(self, data):
        # Reuse the validation logic from SubscriptionSerializer
        subscription_serializer = SubscriptionSerializer(instance=self.instance, data=data, partial=True)
        subscription_serializer.is_valid(raise_exception=True)
        return data

class AllOrgBillingSummarySerializer(serializers.Serializer):
    """
    Flattens Organization + Subscription data for the Super Admin Billing Dashboard.
    """
    org_id = serializers.IntegerField(source='id')
    org_name = serializers.CharField(source='name')
    domain = serializers.CharField()
    owner_email = serializers.SerializerMethodField()
    
    # Subscription Details
    plan_name = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    renewal_date = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    
    # Usage Stats
    users_used = serializers.IntegerField(source='user_count', read_only=True)
    users_limit = serializers.SerializerMethodField()
    storage_limit = serializers.SerializerMethodField()
    testcases_used = serializers.SerializerMethodField()
    testcases_limit = serializers.SerializerMethodField()

    def get_owner_email(self, obj):
        # Efficiently found via prefetch in the View
        owner = next((u for u in obj.users.all() if u.role == 'OWNER'), None)
        return owner.email if owner else "No Owner"

    def _get_active_sub(self, obj):
        # Helper to find the active subscription for this org's owner
        owner = next((u for u in obj.users.all() if u.role == 'OWNER'), None)
        if owner and hasattr(owner, 'subscriptions'):
            # Return the last active, or just the last created one
            return next((s for s in owner.subscriptions.all() if s.is_active), None)
        return None

    def get_plan_name(self, obj):
        sub = self._get_active_sub(obj)
        return sub.get_billing_cycle_display() if sub else "No Plan"

    def get_status(self, obj):
        sub = self._get_active_sub(obj)
        if not sub: return "No Subscription"
        return "Active" if sub.is_active else "Inactive"

    def get_renewal_date(self, obj):
        sub = self._get_active_sub(obj)
        return sub.end_date if sub else None

    def get_amount(self, obj):
        sub = self._get_active_sub(obj)
        return sub.calculate_cost() if sub else 0.00

    def get_users_limit(self, obj):
        sub = self._get_active_sub(obj)
        return sub.selected_users if sub else 5 # Default free limit

    def get_storage_limit(self, obj):
        sub = self._get_active_sub(obj)
        return sub.selected_storage_gb if sub else 10 # Default free limit
    
    def get_testcases_limit(self, obj):
        """
        Returns the purchased testcase limit from the subscription.
        Defaults to 500 (Base limit) if no subscription exists.
        """
        sub = self._get_active_sub(obj)
        # Assuming 'selected_testcases' is the field name in your Subscription model
        return sub.selected_testcases if sub else 500 

    def get_testcases_used(self, obj):
        """
        Returns the number of testcases used.
        Ideally, this comes from an annotation 'testcase_count' in the View.
        """
        return getattr(obj, 'testcase_count', 0)