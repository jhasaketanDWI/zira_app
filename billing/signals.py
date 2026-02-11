from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Subscription, Invoice

@receiver(post_save, sender=Subscription)
def create_subscription_invoice(sender, instance, created, **kwargs):
    """
    Automatically creates an Invoice whenever a new Subscription is created.
    """
    if created:
        # 1. Calculate the cost based on the PricingConfig
        amount = instance.calculate_cost()
        
        # 2. Create the unpaid invoice
        Invoice.objects.create(
            subscription=instance,
            amount=amount,
            period_start=instance.start_date,
            period_end=instance.end_date,
            is_paid=False
        )