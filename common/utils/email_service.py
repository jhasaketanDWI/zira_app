import threading
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string

class EmailThread(threading.Thread):
    def __init__(self, subject, recipient_list, html_message):
        self.subject = subject
        self.recipient_list = recipient_list
        self.html_message = html_message
        threading.Thread.__init__(self)

    def run(self):
        try:
            # Send distinct emails or bulk? 
            # For "one by one" requirement, we loop. 
            # For bulk announcements, we usually use bcc, but here we loop to ensure delivery.
            send_mail(
                subject=self.subject,
                message="",
                from_email=settings.EMAIL_HOST_USER,
                recipient_list=self.recipient_list,
                html_message=self.html_message,
                fail_silently=True,
            )
        except Exception as e:
            print(f"Failed to send email: {e}")


def send_notification_email(subject, recipients, template_path, context):
    """
    Standard interface for sending notifications.
    recipients: list of email strings ['a@b.com', 'c@d.com']
    """
    if not recipients:
        return

    # Render HTML
    html_content = render_to_string(template_path, context)

    # Filter out empty emails and duplicates
    valid_recipients = list(set([r for r in recipients if r]))

    # Launch Thread
    EmailThread(subject, valid_recipients, html_content).start()

# --- HELPER method to Get Standard Recipients ---
def get_stakeholders_emails(project):
    """
    Returns list of emails for: Owner, Admins, Project Managers, Scrum Masters
    """
    from user.models import User
    from project.models import ProjectMember

    emails = set()
    
    # 1. Project Owner
    if project.owner.email:
        emails.add(project.owner.email)

    # 2. System Admins (Superusers)
    admins = User.objects.filter(is_superuser=True).values_list('email', flat=True)
    emails.update(admins)

    # 3. Project Managers & Scrum Masters
    managers = ProjectMember.objects.filter(
        project=project, 
        role__in=['PROJECT_MANAGER', 'SCRUM_MASTER']
    ).values_list('user__email', flat=True)
    emails.update(managers)

    return list(emails)

def get_all_project_members_emails(project):
    """Returns emails of EVERYONE in the project + Owner + Admin"""
    emails = set(get_stakeholders_emails(project)) # Get the bosses
    
    # Add regular members
    members = project.projectmember_set.values_list('user__email', flat=True)
    emails.update(members)
    
    return list(emails)