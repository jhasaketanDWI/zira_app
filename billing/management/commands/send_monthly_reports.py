from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.conf import settings
from billing.models import Subscription, Invoice
from common.utils.email_service import send_notification_email

User = get_user_model()

class Command(BaseCommand):
    help = 'Generates monthly usage reports and renewal invoices.'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        self.stdout.write(f"Starting Report Job for {today}...")

        # 1. Fetch the Single Admin Email
        admin_user = User.objects.filter(role='ADMIN').first()
        if not admin_user:
            admin_user = User.objects.filter(is_superuser=True).first()
        
        # Format as list for CC, or empty list if no admin found
        admin_cc_list = [admin_user.email] if (admin_user and admin_user.email) else []

        # 2. Process Subscriptions
        active_subs = Subscription.objects.filter(is_active=True)
        
        for sub in active_subs:
            try:
                self.process_subscription(sub, today, admin_cc_list)
            except Exception as e:
                self.stderr.write(f"Error processing sub {sub.id}: {e}")

        self.stdout.write(self.style.SUCCESS('Job Complete.'))

    def process_subscription(self, sub, today, admin_cc_list):
        # ... (Usage calculation logic remains the same) ...
        usage_data = {
            'users_used': 'N/A', # Replace with real count
            'users_limit': sub.selected_users,
            'storage_limit': sub.selected_storage_gb,
            'tests_limit': sub.selected_testcases
        }

        # Bill Monthly Users
        is_billed = False
        amount = 0.00
        
        if sub.billing_cycle == 'MONTHLY':
            is_billed = True
            amount = sub.calculate_cost()
            Invoice.objects.create(
                subscription=sub,
                amount=amount,
                period_start=today,
                period_end=today + timezone.timedelta(days=30),
                paid=True,
                external_ref=f"AUTO-{today.strftime('%Y%m')}-{sub.id}"
            )
        
        elif sub.billing_cycle == 'FREE_TRIAL':
            if sub.end_date and sub.end_date <= today:
                # Send Expiry Alert instead of Report
                self.send_expiry_alert(sub, admin_cc_list)
                return

        # Send Report
        self.send_report_email(sub, usage_data, is_billed, amount, admin_cc_list)

    def send_report_email(self, sub, usage, is_billed, amount, admin_cc_list):
        subject = f"Monthly Report: {sub.owner.organization_name if hasattr(sub.owner, 'organization_name') else 'User'}"
        
        msg = f"Monthly billing processed: ${amount}." if is_billed else "Monthly usage summary for your annual plan."

        send_notification_email(
            subject=subject,
            recipients=[sub.owner.email],
            cc=admin_cc_list,  # <--- Single Admin receives copy
            template_path="emails/generic_notification.html",
            context={
                'title': "Monthly Statement",
                'message_body': msg,
                'details': {
                    'Plan': sub.get_billing_cycle_display(),
                    'Status': 'PAID' if is_billed else 'ACTIVE',
                    'Users Limit': usage['users_limit'],
                    'Storage Limit': f"{usage['storage_limit']} GB",
                },
                'action_url': f"{settings.FRONTEND_URL}/billing/invoices"
            }
        )

    def send_expiry_alert(self, sub, admin_cc_list):
        send_notification_email(
            subject="Free Trial Expired",
            recipients=[sub.owner.email],
            cc=admin_cc_list,
            template_path="emails/generic_notification.html",
            context={
                'title': "Trial Ended",
                'message_body': "Your 4-month trial has expired.",
                'details': {'Action': 'Please Upgrade'},
                'action_url': f"{settings.FRONTEND_URL}/billing"
            }
        )