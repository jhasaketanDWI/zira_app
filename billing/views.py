from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from common.permissions import RBACPermission
from django.db.models import Sum, Count
from django.db.models.functions import TruncMonth
from django.contrib.auth import get_user_model
from django.conf import settings

from .models import Subscription, Invoice, PricingConfig
from .serializers import (
    SubscriptionSerializer, 
    InvoiceSerializer, 
    PricingConfigSerializer, 
    BillingReportSerializer
)
from common.utils.email_service import send_notification_email
User = get_user_model()


class SubscriptionViewSet(viewsets.ModelViewSet):
    """
    Manages dynamic subscriptions.
    - Admins: Can see/edit all.
    - Owners/Scrum Masters: Can view and upgrade their own org's plan.
    """
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    
    # NEW PERMISSION MAP (Using the permissions defined in models.py)
    perms_map = {
        # 'view_subscription_plan' should be assigned to Owner, Scrum Master, maybe Devs
        'list': 'billing.view_subscription_plan',
        'retrieve': 'billing.view_subscription_plan',
        
        # 'manage_subscription_plan' should only be Owner or Billing Admin
        'create': 'billing.manage_subscription_plan',
        'update': 'billing.manage_subscription_plan',
        'partial_update': 'billing.manage_subscription_plan',
        'destroy': 'billing.manage_subscription_plan',
    }

    def get_queryset(self):
        user = self.request.user
        # ADMIN OVERRIDE: Admin sees everything
        if getattr(user, 'role', '') == 'ADMIN' or user.is_staff or user.is_superuser:
            return Subscription.objects.all()
        # REGULAR USER: Sees only their own subscription
        return Subscription.objects.filter(owner=user)
    def _get_admin_emails(self):
        """Helper to get all Admin emails for notifications."""
        admin_user = User.objects.filter(role='ADMIN').first()
        
        # Fallback: Try finding a superuser if no role='ADMIN' is found
        if not admin_user:
            admin_user = User.objects.filter(is_superuser=True).first()

        if admin_user and admin_user.email:
            return [admin_user.email] # Return as list for the CC field
        return []
    def perform_create(self, serializer):
        # Admin can create for others, but default to self if not specified
        subscription = serializer.save(
            owner=self.request.user,
            created_by=self.request.user,
            updated_by=self.request.user
        )
        self._send_subscription_email(subscription, is_new=True)
        


    def perform_update(self, serializer):
        subscription = serializer.save(updated_by=self.request.user)
        self._send_subscription_email(subscription, is_new=False)

    def _send_subscription_email(self, subscription, is_new=False):
        """
        Consolidated logic to send emails to User AND Admin.
        """
        cost = subscription.calculate_cost()
        user_email = self.request.user.email
        admin_emails = self._get_admin_emails() # Fetch Admins

        if is_new:
            subject = f"Welcome to {subscription.get_billing_cycle_display()}"
            title = "Subscription Activated"
            message = f"You have successfully activated the {subscription.get_billing_cycle_display()} plan."
        else:
            subject = "Subscription Plan Updated"
            title = "Plan Resources Updated"
            message = "Your subscription resources have been adjusted."

        # Send Email (User gets main, Admins get BCC/Copy)
        send_notification_email(
            subject=subject,
            recipients=[user_email], # Main Recipient
            cc=admin_emails,         # Admins get a copy
            template_path="emails/generic_notification.html",
            context={
                'title': title,
                'message_body': message,
                'details': {
                    'User': self.request.user.get_full_name(),
                    'Org': getattr(self.request.user, 'organization_name', 'N/A'),
                    'Users Count': subscription.selected_users,
                    'Storage': f"{subscription.selected_storage_gb} GB",
                    'Testcases': subscription.selected_testcases,
                    'Cost': "Free" if cost == 0 else f"${cost}",
                    'Renews On': str(subscription.end_date)
                },
                'action_url': f"{settings.FRONTEND_URL}/billing"
            }
        )

class InvoiceViewSet(viewsets.ModelViewSet):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    
    perms_map = {
        'list': 'billing.view_invoices',
        'retrieve': 'billing.view_invoices',
        # Usually only system/admin creates invoices, but if users can generate them:
        'create': 'billing.pay_invoice', 
    }

    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'role', '') == 'ADMIN' or user.is_staff:
            return Invoice.objects.all()
        return Invoice.objects.filter(subscription__owner=user)
    

class PricingConfigViewSet(viewsets.ModelViewSet):
    """
    API for the Admin Panel to manage base prices (e.g., change User cost from $1 to $2).
    """
    queryset = PricingConfig.objects.all()
    serializer_class = PricingConfigSerializer
    permission_classes = [IsAuthenticated, RBACPermission]

    perms_map = {
        'list': 'billing.manage_pricing_config',   # Define this in your RBAC system
        'update': 'billing.manage_pricing_config',
        'partial_update': 'billing.manage_pricing_config',
    }

    def get_queryset(self):
        # Only fetch the single active config
        return PricingConfig.objects.all()

    def update(self, request, *args, **kwargs):
        # Security: Double check it's an ADMIN
        if getattr(request.user, 'role', '') != 'ADMIN' and not request.user.is_superuser:
            return Response({"error": "Only Admins can change pricing."}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)


class BillingReportsViewSet(viewsets.ViewSet):
    """
    New Feature: Reports & Analytics
    Returns aggregated data for frontend charts (Spending over time).
    """
    permission_classes = [IsAuthenticated, RBACPermission]
    perms_map = {
        'list': 'billing.view_reports', # Usually Owner/Admin
    }

    def list(self, request):
        user = request.user
        
        # 1. Admin sees GLOBAL revenue
        if getattr(user, 'role', '') == 'ADMIN' or user.is_superuser:
            queryset = Invoice.objects.all()
        # 2. Users see THEIR spending
        else:
            queryset = Invoice.objects.filter(subscription__owner=user)

        # AGGREGATION QUERY: Group invoices by month
        # Output format: [{month: "2025-01-01", total_spend: 100.00}, ...]
        report_data = (
            queryset
            .annotate(month=TruncMonth('period_start'))
            .values('month')
            .annotate(
                total_spend=Sum('amount'),
                invoice_count=Count('id')
            )
            .order_by('month')
        )
        
        # Format for React (Recharts friendly)
        formatted_data = [
            {
                "name": entry['month'].strftime("%b %Y"), # e.g., "Jan 2026"
                "spend": entry['total_spend'],
                "invoices": entry['invoice_count']
            }
            for entry in report_data
        ]

        return Response({
            "chart_data": formatted_data,
            "summary": {
                "total_spent_lifetime": sum(item['spend'] for item in formatted_data),
                "last_month_spend": formatted_data[-1]['spend'] if formatted_data else 0
            }
        })
