from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action, api_view, permission_classes
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
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
import requests
from django.core.files.storage import FileSystemStorage
import os
from django.core.mail import EmailMessage



from .models import Subscription, Invoice, PricingConfig, DiscountCode, Payment
from .serializers import (
    SubscriptionSerializer, 
    InvoiceSerializer, 
    PricingConfigSerializer, 
    BillingReportSerializer,
    AllOrgBillingSummarySerializer,
    DiscountCodeSerializer,
    PaymentSerializer
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



# --- Cashfree Payment Logic ---

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_cashfree_order(request):
    """
    Initiates a Cashfree order for a specific Invoice.
    """
    try:
        data = request.data
        invoice_id = data.get("invoice_id")
        
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        user = request.user

        # Ensure user owns this subscription
        if invoice.subscription.owner != user:
             return Response({"error": "Unauthorized access to invoice"}, status=403)

        # Ensure amount matches invoice amount
        total_amount = invoice.amount 
        total_amount = Decimal(total_amount).quantize(Decimal('0.01'))

        if total_amount <= 0:
            return Response({"error": "Invalid invoice amount"}, status=400)

        # Generate unique order ID
        order_id = f"ORD_{timezone.now().strftime('%Y%m%d%H%M%S')}_{user.id}_{invoice.id}"

        headers = {
            "Content-Type": "application/json",
            "x-client-id": settings.CASHFREE_APP_ID,
            "x-client-secret": settings.CASHFREE_SECRET_KEY,
            "x-api-version": "2022-01-01"
        }
        payload = {
            "order_id": order_id,
            "order_amount": float(total_amount),  
            "order_currency": "INR",
            "customer_details": {
                "customer_id": str(user.id),
                "customer_name": user.get_full_name() or user.email,
                "customer_email": user.email,
                "customer_phone": getattr(user, 'phone', '9999999999'), # Fallback
            },
            "order_meta": {
                "return_url": f"{settings.FRONTEND_URL}/billing/redirecting?order_id={{order_id}}"
            }
        }

        response = requests.post(settings.CASHFREE_API_URL, json=payload, headers=headers)
        response_data = response.json()

        if "payment_link" in response_data:
            # Create a pending Payment record
            Payment.objects.create(
            invoice=invoice,
            amount_paid=total_amount,  # Correct field name from models.py
            payment_status="PENDING",
            transaction_id=order_id,
            created_by=user
        )
            return Response({"payment_link": response_data["payment_link"], "order_id": order_id})

        return Response({"error": "Failed to create payment order", "details": response_data}, status=400)

    except Exception as e:
        print("Error:", str(e))
        return Response({"error": "An internal error occurred"}, status=500)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_cashfree_order(request):
    """
    Verifies payment status with Cashfree after redirect.
    """
    data = request.data
    order_id = data.get("order_id")

    headers = {
        "Content-Type": "application/json",
        "x-client-id": settings.CASHFREE_APP_ID,
        "x-client-secret": settings.CASHFREE_SECRET_KEY,
        "x-api-version": "2022-01-01"
    }

    # IMPORTANT: Use the same environment (sandbox/prod) as creation
    # Extract base URL from settings or hardcode logic
    base_url = settings.CASHFREE_API_URL.replace("/pg/orders", "") 
    verify_url = f"{base_url}/pg/orders/{order_id}"
    
    response = requests.get(verify_url, headers=headers)
    response_data = response.json()

    payment = Payment.objects.filter(transaction_id=order_id).first()

    if not payment:
        return Response({"error": "Payment record not found"}, status=404)

    order_status = response_data.get("order_status")

    if order_status == "PAID":
        payment.payment_status = "SUCCESS"
        # Store actual CF payment ID if available
        # payment.transaction_id = response_data.get("cf_payment_id", payment.transaction_id) 
        payment.save()

        # Update Invoice
        invoice = payment.invoice
        invoice.is_paid = True
        invoice.transaction_id = order_id
        invoice.save()

        # Update Subscription Status
        sub = invoice.subscription
        sub.is_active = True
        
        # Handle Discount Usage Count
        if sub.applied_discount and sub.applied_discount.is_valid():
            sub.applied_discount.use_code()
            
        sub.save()
            # serializer = SubscriptionSerializer(sub)
            # return Response(serializer.data)

        return Response({"status": "success", "message": "Payment verified and subscription active"})

    elif order_status in ["FAILED", "EXPIRED", "CANCELLED"]:
        payment.payment_status = "FAILED"
        payment.save()
        return Response({"status": "failed", "message": "Payment not successful"})

    return Response({"status": "pending", "message": "Payment still pending"})


class DiscountCodeViewSet(viewsets.ModelViewSet):
    """
    CRUD for Discount Codes. 
    Only Admin/SuperUser should be able to create/list all.
    Users can 'retrieve' to check validity via a specific action if needed.
    """
    queryset = DiscountCode.objects.all()
    serializer_class = DiscountCodeSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin] 

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def validate_code(self, request):
        """
        Public endpoint for users to check if a code is valid before purchasing.
        """
        code = request.data.get('code')
        try:
            discount = DiscountCode.objects.get(code=code)
            if discount.is_valid():
                return Response({
                    "valid": True,
                    "type": discount.discount_type,
                    "value": discount.discount_value
                })
            else:
                return Response({"valid": False, "error": "Code expired or limit reached."}, status=400)
        except DiscountCode.DoesNotExist:
            return Response({"valid": False, "error": "Invalid code."}, status=404)

# class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
#     """
#     Handle Payments.
#     """
#     queryset = Payment.objects.all()
#     serializer_class = PaymentSerializer
#     permission_classes = [IsAuthenticated]

#     def create(self, request, *args, **kwargs):
#         """
#         Manual payment recording (simulated).
#         """
#         invoice_id = request.data.get('invoice')
#         amount_paid = request.data.get('amount_paid')
        
#         invoice = get_object_or_404(Invoice, pk=invoice_id)
        
#         # Verify ownership
#         if not request.user.is_super_admin and invoice.subscription.owner.organization != request.user.organization:
#              return Response({"error": "Not authorized for this invoice"}, status=403)

#         with transaction.atomic():
#             # 1. Create Payment
#             payment_data = {
#                 'invoice': invoice.id,
#                 'amount_paid': amount_paid,
#                 'payment_status': 'SUCCESS', # Assuming direct success for this API
#                 'transaction_id': request.data.get('transaction_id')
#             }
#             serializer = self.get_serializer(data=payment_data)
#             serializer.is_valid(raise_exception=True)
#             payment = serializer.save()

#             # 2. Update Invoice
#             invoice.is_paid = True
#             invoice.transaction_id = payment.transaction_id
#             invoice.save()

#             # 3. Handle Discount Usage if applicable
#             sub = invoice.subscription
#             if sub.applied_discount and sub.applied_discount.is_valid():
#                 sub.applied_discount.use_code()

#             # 4. Activate Subscription if strictly waiting for payment
#             # (Logic depends on if you activate on creation or payment)
            
#             return Response(serializer.data, status=status.HTTP_201_CREATED)
class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only view for user payments history.
    """
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return Payment.objects.all()
        return Payment.objects.filter(invoice__subscription__owner__organization=user.organization)

    @action(detail=False, methods=['post'])
    def send_invoice_email(self, request):
        """
        Sends an invoice PDF via email.
        Expected Payload: { 'email': '...', 'file': (binary) }
        """
        email = request.data.get('email')
        pdf_file = request.FILES.get('file')

        if not email or not pdf_file:
            return Response({'message': 'Email and file are required'}, status=400)

        # Save the file temporarily
        fs = FileSystemStorage(location=settings.MEDIA_ROOT)
        filename = fs.save(f"invoices/{pdf_file.name}", pdf_file)
        full_file_path = fs.path(filename)

        try:
            subject = 'Your Invoice from Jira Clone'
            message = 'Please find attached the invoice for your recent payment.'
            from_email = settings.EMAIL_HOST_USER

            email_message = EmailMessage(subject, message, from_email, [email])
            email_message.attach_file(full_file_path)
            email_message.send()
            
            # Cleanup
            os.remove(full_file_path)
            return Response({'message': 'Email sent successfully'})
        except Exception as e:
            return Response({'message': f'Failed to send email: {str(e)}'}, status=500)

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
        subscription = serializer.save(owner=self.request.user)
        self._send_notification(subscription, "Subscription Activated")

    def perform_update(self, serializer):
        subscription = serializer.save()
        self._send_notification(subscription, "Subscription Updated")

    def _send_notification(self, subscription, title):
        organization = subscription.owner.organization
        recipients = get_billing_notification_recipients(organization)
        org_name = organization.name if organization else "Unknown Organization"

        send_notification_email(
            subject=f"{title}: {org_name}",
            recipients=recipients,
            template_path="emails/notification.html",
            context={
                'title': title,
                'message_body': f"Subscription for {org_name} has been processed.",
                'details': {
                    'Organization': org_name,
                    'Plan': subscription.get_billing_cycle_display(),
                    'New Limit': f"{subscription.selected_users} Users",
                    'Updated By': self.request.user.get_full_name(),
                    'Cost': f"${subscription.calculate_cost()}",
                    'Discount': subscription.applied_discount.code if subscription.applied_discount else "None"
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