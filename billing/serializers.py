from rest_framework import serializers
from .models import Subscription, PricingConfig, Invoice
from decimal import Decimal

class SubscriptionSerializer(serializers.ModelSerializer):
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    total_price = serializers.SerializerMethodField()
    formatted_status = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            'id', 'owner', 'selected_users', 'selected_storage_gb', 
            'selected_testcases', 'billing_cycle', 'start_date', 
            'end_date', 'is_active', 'total_price', 'formatted_status'
        ]
        read_only_fields = ['start_date', 'end_date', 'is_active', 'price_at_activation']

    def get_total_price(self, obj):
        return obj.calculate_cost()
    
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