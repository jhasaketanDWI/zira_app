from rest_framework_nested import routers
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    SubscriptionViewSet,
    InvoiceViewSet,
    PricingConfigViewSet,    
    BillingReportsViewSet,
    SuperAdminBillingDashboardView,
    SuperAdminOrganizationDetailsView,
)

router = DefaultRouter()

router.register(r'subscriptions', SubscriptionViewSet, basename='subscription')
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'config', PricingConfigViewSet, basename='pricing-config')
router.register(r'reports', BillingReportsViewSet, basename='billing-reports')

urlpatterns = [
    path('admin/subscriptions/dashboard/', SuperAdminBillingDashboardView.as_view(), name='admin-billing-dashboard'),
    path('admin/subscriptions/organizations/<int:org_id>/', SuperAdminOrganizationDetailsView.as_view(), name='admin-org-billing-details'),

    
    path('billing/', include(router.urls)),
    
]