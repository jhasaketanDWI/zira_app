from django.shortcuts import render
from rest_framework import viewsets, permissions
from common.utils import get_client_ip
from .models import SubscriptionPlan, Subscription, Invoice
from .serializers import SubscriptionPlanSerializer, SubscriptionSerializer, InvoiceSerializer

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
        ip = get_client_ip(self.request)
        # Corrected to use the 'created_by' and 'updated_by' fields from AuditBaseModel.
        serializer.save(created_by=ip, updated_by=ip)

    def perform_update(self, serializer):
        ip = get_client_ip(self.request)
        # Corrected to use the 'updated_by' field.
        serializer.save(updated_by=ip)


class SubscriptionViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to view and manage their own subscriptions.
    """
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        This is a critical security correction.
        It ensures that users can only view their own subscriptions and not anyone else's.
        """
        return Subscription.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        ip = get_client_ip(self.request)
        # The owner is automatically set to the currently logged-in user.
        serializer.save(
            owner=self.request.user,
            created_by=ip,
            updated_by=ip,
        )

    def perform_update(self, serializer):
        ip = get_client_ip(self.request)
        serializer.save(updated_by=ip)


class InvoiceViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to view invoices for their subscriptions.
    """
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """
        This is another critical security correction.
        It ensures users can only see invoices that belong to their subscriptions.
        """
        return Invoice.objects.filter(subscription__owner=self.request.user)

    def perform_create(self, serializer):
        ip = get_client_ip(self.request)
        serializer.save(created_by=ip, updated_by=ip)

    def perform_update(self, serializer):
        ip = get_client_ip(self.request)
        serializer.save(updated_by=ip)

