from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction
from dateutil.relativedelta import relativedelta
from billing.models import Subscription, Invoice
from common.utils.email_service import send_notification_email
from billing.views import get_billing_notification_recipients # Reuse the helper

User = get_user_model()

class Command(BaseCommand):
    help = 'Generates monthly usage reports and renewal invoices for subscriptions expiring TODAY.'

    def handle(self, *args, **kwargs):
        today = timezone.now().date()
        self.stdout.write(f"Starting Billing Job for {today}...")

        # 1. CRITICAL: Only process active subscriptions where end_date == TODAY
        active_subs = Subscription.objects.filter(is_active=True, end_date=today)
        
        count = active_subs.count()
        if count == 0:
            self.stdout.write("No subscriptions due for renewal today.")
            return

        self.stdout.write(f"Found {count} subscriptions to process.")

        for sub in active_subs:
            try:
                # Wrap each subscription in atomic transaction
                # If invoice fails, date shouldn't update, and vice versa.
                with transaction.atomic():
                    self.process_subscription(sub, today)
            except Exception as e:
                self.stderr.write(f"Error processing sub {sub.id}: {e}")

        self.stdout.write(self.style.SUCCESS('Billing Job Complete.'))

    def process_subscription(self, sub, today):
        # 1. Calculate Cost
        amount = sub.calculate_cost()
        is_billed = sub.billing_cycle in ['MONTHLY', 'YEARLY']
        
        invoice = None
        if is_billed:
            # Create Invoice
            invoice = Invoice.objects.create(
                subscription=sub,
                amount=amount,
                period_start=today,
                # Assuming next bill is 1 month or 1 year away
                period_end=today + relativedelta(months=1 if sub.billing_cycle == 'MONTHLY' else 12),
                is_paid=False # Mark as unpaid initially
            )
            self.stdout.write(f"Created Invoice #{invoice.id} for {sub.owner.email}")

        # 2. CRITICAL: Update the Subscription end_date
        # Move it forward so we don't bill them again tomorrow
        if sub.billing_cycle == 'MONTHLY':
            sub.end_date = sub.end_date + relativedelta(months=1)
        elif sub.billing_cycle == 'YEARLY':
            sub.end_date = sub.end_date + relativedelta(years=1)
        elif sub.billing_cycle == 'FREE_TRIAL':
            # Trial expired today
            sub.is_active = False # Deactivate
            self.send_expiry_alert(sub)
            sub.save()
            return # Stop processing, no invoice email needed here (expiry email sent)
        
        sub.save()

        # 3. Send Email Notification
        organization = sub.owner.organization
        recipients = get_billing_notification_recipients(organization)
        
        subject = f"Invoice Generated: {organization.name}" if is_billed else "Monthly Usage Report"
        message_body = (
            f"A new invoice for ${amount} has been generated for {organization.name}." 
            if is_billed 
            else "Here is your monthly usage summary."
        )

        send_notification_email(
            subject=subject,
            recipients=recipients,
            template_path="emails/notification.html",
            context={
                'title': "Billing Update",
                'message_body': message_body,
                'details': {
                    'Organization': organization.name,
                    'Plan': sub.get_billing_cycle_display(),
                    'Amount': f"${amount}",
                    'Next Due': sub.end_date.strftime("%Y-%m-%d")
                },
                'action_url': f"{settings.FRONTEND_URL}/billing/invoices"
            }
        )

    def send_expiry_alert(self, sub):
        organization = sub.owner.organization
        recipients = get_billing_notification_recipients(organization)

        send_notification_email(
            subject=f"Trial Expired: {organization.name}",
            recipients=recipients,
            template_path="emails/notification.html",
            context={
                'title': "Free Trial Ended",
                'message_body': "Your free trial has expired. Please upgrade to continue using premium features.",
                'details': {
                    'Organization': organization.name,
                    'Status': 'Inactive'
                },
                'action_url': f"{settings.FRONTEND_URL}/billing/upgrade"
            }
        )