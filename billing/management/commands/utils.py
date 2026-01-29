from django.contrib.auth import get_user_model

User = get_user_model()

def get_billing_notification_recipients(organization):
    """
    Returns a distinct list of emails for:
    1. Super Admins (System)
    2. Organization Owner
    3. Organization Scrum Masters
    """
    if not organization:
        return []

    emails = set()

    # 1. Super Admins
    emails.update(User.objects.filter(is_superuser=True).values_list('email', flat=True))

    # 2. Organization Owner & Scrum Masters
    # We query users belonging to this specific org with specific roles
    org_stakeholders = User.objects.filter(
        organization=organization,
        role__in=['OWNER', 'SCRUM_MASTER'],
        is_active=True
    ).values_list('email', flat=True)
    
    emails.update(org_stakeholders)

    # Remove None/Empty strings just in case
    return list(filter(None, emails))