import threading
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
class EmailThread(threading.Thread):
    def __init__(self, subject, recipient_list, html_message,bcc=None, cc=None):
        self.subject = subject
        self.recipient_list = recipient_list
        self.html_message = html_message
        self.bcc = bcc if bcc else []
        self.cc = cc if cc else []
        threading.Thread.__init__(self)

    def run(self):
        try:
            # 1. Create the plain text version (for email clients that block HTML)
            text_content = strip_tags(self.html_message)
           # 2. Construct the Email Object
            msg = EmailMultiAlternatives(
                subject=self.subject,
                body=text_content, # Plain text content
                from_email=settings.EMAIL_HOST_USER,
                to=self.recipient_list, 
                bcc=self.bcc,           
                cc=self.cc              
            )
            # 3. Attach HTML Content
            msg.attach_alternative(self.html_message, "text/html")
            
            # 4. Send
            msg.send(fail_silently=True)
            # send_mail(
            #     subject=self.subject,
            #     message="",
            #     from_email=settings.EMAIL_HOST_USER,
            #     recipient_list=self.recipient_list,
            #     html_message=self.html_message,
            #     fail_silently=True,
            # )
        except Exception as e:
            print(f"Failed to send email: {e}")


def send_notification_email(subject, recipients, template_path, context,bcc=None, cc=None):
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
    EmailThread(subject, valid_recipients, html_content, bcc=bcc, cc=cc).start()

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