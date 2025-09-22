from rest_framework import serializers
from .models import SubscriptionPlan, Subscription,  Invoice
       
class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = '__all__'


class SubscriptionSerializer(serializers.ModelSerializer):
    # The 'owner' field is made read-only because it's automatically assigned
    # to the logged-in user in the view, not sent in the request body.
    owner = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Subscription
        fields = '__all__'  


class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = '__all__'
        
