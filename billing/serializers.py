from rest_framework import serializers
from .models import Subscription, PricingConfig, Invoice

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
        cycle = data.get('billing_cycle')

        config = PricingConfig.objects.first()
        if not config:
            raise serializers.ValidationError("System configuration missing.")

        # 1. Zero State Check
        if users == 0 and storage == 0 and testcases == 0:
             return data # Valid "cancelled" state

        # 2. Lakadi Free Plan Logic
        if cycle == 'FREE_TRIAL':
            if users != 5 or storage != 10 or testcases != 500:
                 raise serializers.ValidationError("Free Plan (Lakadi) is fixed at 5 Users, 10GB, 500 Testcases.")
            return data

        # 3. Minimum User Logic (Jump 0 -> 5)
        if users < config.min_users:
            raise serializers.ValidationError({"selected_users": f"Minimum users allowed is {config.min_users}."})

        # 4. Storage Logic (Base 10GB + 2GB per extra user)
        # Calculate dynamic minimum
        extra_users = users - config.min_users
        min_storage = config.min_storage_base + (extra_users * config.storage_per_user_step)
        
        if storage < min_storage:
             raise serializers.ValidationError({
                 "selected_storage_gb": f"For {users} users, storage cannot be less than {min_storage}GB."
             })

        # 5. Testcase Logic (Steps of 500)
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
    Serializer to format data for Frontend Charts (Recharts/Chart.js).
    """
    month = serializers.CharField()
    total_spend = serializers.DecimalField(max_digits=10, decimal_places=2)
    invoice_count = serializers.IntegerField()