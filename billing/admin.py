from django.contrib import admin
from .models import Subscription, Invoice, PricingConfig

@admin.register(PricingConfig)
class PricingConfigAdmin(admin.ModelAdmin):
    # This ensures you can edit the prices ($1 user, $1 gb) from Django Admin
    list_display = ('price_per_user', 'price_per_gb', 'min_users', 'updated_at')

admin.site.register(Subscription)
admin.site.register(Invoice)
