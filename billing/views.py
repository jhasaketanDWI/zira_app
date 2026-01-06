from django.shortcuts import render
from rest_framework import viewsets, permissions
from common.permissions import RBACPermission
from rest_framework.permissions import IsAuthenticated
from .models import SubscriptionPlan, Subscription, Invoice
from .serializers import SubscriptionPlanSerializer, SubscriptionSerializer, InvoiceSerializer
from common.utils.email_service import send_notification_email
from django.conf import settings


class SubscriptionPlanViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows subscription plans to be viewed or edited.
    Only admin users can modify subscription plans.
    """
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    # Permissions are set to IsAdminUser, as typically only admins should manage plans.
    permission_classes = [permissions.IsAdminUser]

    def perform_create(self, serializer):
        # Save the user who created and updated the plan
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        # Update the user who modified the plan
        serializer.save(updated_by=self.request.user)


class SubscriptionViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to view and manage their own subscriptions.
    """
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    perms_map = {
        # Viewing subscription details requires permission (usually Owner/Billing Admin)
        'list': 'billing.can_manage_subscription',
        'retrieve': 'billing.can_manage_subscription',

        # Creating/Upgrading plans
        'create': 'billing.can_manage_subscription',
        'update': 'billing.can_manage_subscription',
        'partial_update': 'billing.can_manage_subscription',

        # Canceling subscription
        'destroy': 'billing.can_manage_subscription',
    }

    def get_queryset(self):
        """
        This is a critical security correction.
        It ensures that users can only view their own subscriptions and not anyone else's.
        """
        return Subscription.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        # The owner is automatically set to the currently logged-in user.
        subscription = serializer.save(
            owner=self.request.user,
            created_by=self.request.user,
            updated_by=self.request.user,
        )
        # [EMAIL] New Subscription Started
        send_notification_email(
            subject=f"Welcome to {subscription.plan.name} Plan",
            recipients=[self.request.user.email],
            template_path="emails/generic_notification.html",
            context={
                'title': "Subscription Started",
                'message_body': f"Thank you for subscribing to the {subscription.plan.name} plan.",
                'details': {
                    'Plan': subscription.plan.name,
                    'Start Date': str(subscription.start_date),
                    'End Date': str(subscription.end_date),
                    'Status': subscription.status
                },
                'action_url': f"{settings.FRONTEND_URL}/billing/subscriptions"
            }
        )

    def perform_update(self, serializer):
        subscription = serializer.save(updated_by=self.request.user)

        # [EMAIL] Subscription Updated
        send_notification_email(
            subject="Subscription Updated",
            recipients=[self.request.user.email],
            template_path="emails/generic_notification.html",
            context={
                'title': "Subscription Plan Updated",
                'message_body': "Your subscription details have been updated.",
                'details': {
                    'Current Plan': subscription.plan.name,
                    'Status': subscription.status,
                    'Updated By': self.request.user.get_full_name()
                },
                'action_url': f"{settings.FRONTEND_URL}/billing/subscriptions"
            }
        )

    def perform_destroy(self, instance):
        # [EMAIL] Subscription Cancelled
        plan_name = instance.plan.name
        send_notification_email(
            subject="Subscription Cancelled",
            recipients=[self.request.user.email],
            template_path="emails/generic_notification.html",
            context={
                'title': "Subscription Cancelled",
                'message_body': f"Your subscription to the {plan_name} plan has been cancelled.",
                'details': {
                    'Plan': plan_name,
                    'Cancelled By': self.request.user.get_full_name()
                },
                'action_url': f"{settings.FRONTEND_URL}/billing"
            }
        )
        instance.delete()


class InvoiceViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to view invoices for their subscriptions.
    """
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated, RBACPermission]
    perms_map = {
        # Viewing invoices
        'list': 'billing.can_view_all_invoices',
        'retrieve': 'billing.can_view_all_invoices',

        # Creating/Editing invoices is typically automated or Admin-only,
        # but if exposed, it requires high-level billing permissions.
        'create': 'billing.can_manage_subscription',
        'update': 'billing.can_manage_subscription',
        'partial_update': 'billing.can_manage_subscription',
        'destroy': 'billing.can_manage_subscription',
    }

    def get_queryset(self):
        """
        This is another critical security correction.
        It ensures users can only see invoices that belong to their subscriptions.
        """
        return Invoice.objects.filter(subscription__owner=self.request.user)

    def perform_create(self, serializer):
        # Use self.request.user for auditing
        invoice = serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user
        )

        # [EMAIL] New Invoice Generated
        # Determine recipient from the related subscription owner
        recipient_email = invoice.subscription.owner.email

        send_notification_email(
            subject=f"New Invoice Available: #{invoice.id}",
            recipients=[recipient_email],
            template_path="emails/generic_notification.html",
            context={
                'title': "Invoice Generated",
                'message_body': "A new invoice has been generated for your subscription.",
                'details': {
                    'Invoice ID': f"#{invoice.id}",
                    'Amount': f"${invoice.amount}",
                    'Plan': invoice.subscription.plan.name,
                    'Date': str(invoice.issue_date)
                },
                'action_url': f"{settings.FRONTEND_URL}/billing/invoices/{invoice.id}"
            }
        )

    def perform_update(self, serializer):
        # Use self.request.user for auditing
        serializer.save(updated_by=self.request.user)