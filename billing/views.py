from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from common.permissions import RBACPermission
from django.db.models import Sum, Count, Prefetch
from django.db.models.functions import TruncMonth
from django.contrib.auth import get_user_model
from django.conf import settings
from decimal import Decimal
from rest_framework.views import APIView
from organizations.models import Organization
from organizations.permissions import IsSuperAdmin


from .models import Subscription, Invoice, PricingConfig
from .serializers import (
    SubscriptionSerializer, 
    InvoiceSerializer, 
    PricingConfigSerializer, 
    BillingReportSerializer,
    AllOrgBillingSummarySerializer
)
from common.utils.email_service import send_notification_email

User = get_user_model()

# --- Helper Function for Email Recipients ---
def get_billing_notification_recipients(organization):
    """
    Returns unique list of emails for:
    1. Super Admins
    2. Organization Owner
    3. Organization Scrum Masters
    """
    recipients = set()

    # 1. Super Admins
    super_admins = User.objects.filter(is_superuser=True).values_list('email', flat=True)
    recipients.update(super_admins)

    if organization:
        # 2. Organization Owner & Scrum Masters
        org_users = User.objects.filter(
            organization=organization,
            role__in=['OWNER', 'SCRUM_MASTER']
        ).values_list('email', flat=True)
        recipients.update(org_users)

    return [email for email in recipients if email]

class SubscriptionViewSet(viewsets.ModelViewSet):
    """
    Manages dynamic subscriptions.
    - Admins: Can see/edit all.
    - Owners/Scrum Masters: Can view and upgrade their own org's plan.
    """
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    
    perms_map = {
        'list': 'billing.view_subscription_plan',
        'retrieve': 'billing.view_subscription_plan',
        'create': 'billing.manage_subscription_plan',
        'update': 'billing.manage_subscription_plan',
        'partial_update': 'billing.manage_subscription_plan',
        'destroy': 'billing.manage_subscription_plan',
    }

    def get_queryset(self):
        user = self.request.user
        
        # Optimize: Fetch related owner and organization
        queryset = Subscription.objects.select_related('owner', 'owner__organization')

        if user.is_superuser:
            return queryset.all()
        
        # Return subscription for the user's organization
        # Assuming one subscription per owner/org
        return queryset.filter(owner__organization=user.organization)

    def perform_create(self, serializer):
        # Create subscription
        subscription = serializer.save(owner=self.request.user)
        
        # Send Email Notification
        organization = subscription.owner.organization
        recipients = get_billing_notification_recipients(organization)
        
        org_name = organization.name if organization else "Unknown Organization"

        send_notification_email(
            subject=f"New Subscription: {org_name}",
            recipients=recipients,
            template_path="emails/notification.html",
            context={
                'title': "Subscription Activated",
                'message_body': f"A new {subscription.get_billing_cycle_display()} plan has been activated for {org_name}.",
                'details': {
                    'Organization': org_name,
                    'Plan': subscription.get_billing_cycle_display(),
                    'Users Limit': subscription.selected_users,
                    'Cost': f"${subscription.calculate_cost()}",
                    'Action By': self.request.user.get_full_name()
                },
                'action_url': f"{settings.FRONTEND_URL}/billing"
            }
        )

    def perform_update(self, serializer):
        subscription = serializer.save()
        
        # Send Email Notification
        organization = subscription.owner.organization
        recipients = get_billing_notification_recipients(organization)
        
        org_name = organization.name if organization else "Unknown Organization"

        send_notification_email(
            subject=f"Plan Updated: {org_name}",
            recipients=recipients,
            template_path="emails/notification.html",
            context={
                'title': "Subscription Updated",
                'message_body': f"The subscription plan for {org_name} has been updated.",
                'details': {
                    'Organization': org_name,
                    'New Plan': subscription.get_billing_cycle_display(),
                    'New Limit': f"{subscription.selected_users} Users",
                    'Updated By': self.request.user.get_full_name()
                },
                'action_url': f"{settings.FRONTEND_URL}/billing"
            }
        )


class InvoiceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only view for invoices.
    """
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = Invoice.objects.select_related('subscription', 'subscription__owner')
        
        if user.is_superuser:
            return qs.all()
        
        return qs.filter(subscription__owner__organization=user.organization)


class PricingConfigViewSet(viewsets.ModelViewSet):
    """
    Admin only: Configure global pricing.
    """
    queryset = PricingConfig.objects.all()
    serializer_class = PricingConfigSerializer
    permission_classes = [IsAuthenticated] 

    def get_permissions(self):
        # Only Superuser can edit pricing
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            # You might want a custom permission here like IsSuperUser
            pass 
        return super().get_permissions()


class BillingReportsViewSet(viewsets.ViewSet):
    """
    Returns aggregated data for charts.
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        user = request.user
        
        # Filter invoices based on permissions
        if user.is_superuser:
            queryset = Invoice.objects.all()
        else:
            queryset = Invoice.objects.filter(subscription__owner__organization=user.organization)

        # 1. GROUP BY MONTH
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
        
        # 2. PREPARE DATA
        data_for_serializer = [
            {
                "month": entry['month'].strftime("%b %Y"),
                "total_spend": entry['total_spend'],
                "invoice_count": entry['invoice_count']
            }
            for entry in report_data
        ]

        # 3. SERIALIZE
        serializer = BillingReportSerializer(data=data_for_serializer, many=True)
        serializer.is_valid(raise_exception=True)
        serialized_data = serializer.data
        
        # 4. SUMMARY CALCULATION (Use Decimal)
        # item['total_spend'] comes as string from serializer, convert to Decimal
        total_lifetime = sum(Decimal(str(item['total_spend'])) for item in serialized_data)
        last_month = serialized_data[-1]['total_spend'] if serialized_data else 0
        
        return Response({
            "chart_data": serialized_data,
            "summary": {
                "total_spent_lifetime": total_lifetime,
                "last_month_spend": last_month
            }
        })

class SuperAdminBillingDashboardView(APIView):
    """
    Aggregates billing data across ALL organizations.
    Endpoint: /api/billing/admin/dashboard/
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        users_prefetch = Prefetch(
            'users',
            queryset=User.objects.order_by('id').prefetch_related('subscriptions')
        )

        orgs = Organization.objects.annotate(
            user_count=Count('users')
        ).prefetch_related(users_prefetch).order_by('-created_at')

        serializer = AllOrgBillingSummarySerializer(orgs, many=True)
        serialized_data = serializer.data

        total_revenue = sum(float(item['amount']) for item in serialized_data if item['status'] == 'Active')
        total_active_subs = sum(1 for item in serialized_data if item['status'] == 'Active')
        total_orgs = len(serialized_data)

        return Response({
            "summary": {
                "total_monthly_revenue": total_revenue,
                "active_subscriptions": total_active_subs,
                "total_organizations": total_orgs
            },
            "organizations": serialized_data
        })

class SuperAdminOrganizationDetailsView(APIView):
    """
    Fetches detailed billing info and invoice history for a SINGLE organization.
    Endpoint: /api/billing/admin/organizations/<int:org_id>/
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request, org_id):
        # 1. Fetch Org with annotations (needed for AllOrgBillingSummarySerializer)
        users_prefetch = Prefetch(
            'users',
            queryset=User.objects.order_by('id').prefetch_related('subscriptions')
        )
        
        try:
            org = Organization.objects.annotate(
                user_count=Count('users', distinct=True),
                testcase_count=Count('projects__testcases', distinct=True)
            ).prefetch_related(users_prefetch).get(pk=org_id)
        except Organization.DoesNotExist:
            return Response({"error": "Organization not found"}, status=status.HTTP_404_NOT_FOUND)

        # 2. Fetch Invoices for this Org
        # Logic: Invoices -> Subscription -> Owner -> Organization
        invoices = Invoice.objects.filter(
            subscription__owner__organization=org
        ).order_by('-period_start')

        # 3. Serialize Data
        summary_serializer = AllOrgBillingSummarySerializer(org)
        invoice_serializer = InvoiceSerializer(invoices, many=True)

        return Response({
            "details": summary_serializer.data,
            "invoices": invoice_serializer.data
        })