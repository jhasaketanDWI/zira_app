import logging
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.db.models import Q

# Configure logging for production visibility
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Initializes Role-Based Access Control (RBAC) groups with default permissions.'

    def handle(self, *args, **options):
        self.stdout.write("Starting Role Initialization...")
        
       
        
        # Base permissions that EVERY staff member needs
        base_permissions = [
            'view_project', 'view_teammember', 'view_task', 
            'add_comment', 'view_comment', 'view_notification',
            'view_page', 'view_sprint', 'view_activitylog'
        ]

        # Role-Specific Permission Sets
        # Note: These codenames match the list you provided
        
        TESTER_PERMS = base_permissions + [
            # QA & Testing
            'can_create_testcase', 'can_edit_testcase', 'can_run_testcases', 
            'can_link_test_to_task', 'can_manage_test_steps', 'can_view_all_testcases',
            'can_create_test_plan', 'can_execute_test_run', 'can_update_execution_status',
            'add_ticket', 'change_ticket', 'view_ticket', # Bug tracking
            'add_qatestcase', 'view_qatestcase',
            'add_testrun', 'view_testrun',
            # Task interaction
            'can_create_task', 'add_attachment',
        ]

        DEVELOPER_PERMS = base_permissions + [
            # Task Management
            'can_create_task', 'can_edit_tasks', 'can_assign_task', 
            'can_change_status', 'can_add_comment', 'can_manage_attachments',
            'can_link_tasks', 'can_edit_story_points', 'can_view_all_tasks',
            # Code & Documentation
            'view_module', 'view_code', 'can_create_page', 'can_edit_page_content',
            # Basic Sprint View
            'view_sprint', 'view_epic'
        ]

        SCRUM_MASTER_PERMS = DEVELOPER_PERMS + [
            # Sprint Lifecycle
            'can_create_sprint', 'can_start_sprint', 'can_end_sprint', 
            'can_move_to_backlog', 'can_edit_sprint',
            # High-Level Planning
            'add_epic', 'change_epic', 'can_create_epic', 
            'add_goal', 'change_goal',
            # Team Management
            'can_invite_team_members', 'can_manage_team_roles', 'can_remove_team_members',
            # Process Configuration
            'can_create_status', 'can_reorder_status', 'can_manage_workflows',
        ]

        MANAGER_PERMS = base_permissions + [
            # Project Oversight
            'can_create_project', 'can_archive_project', 'can_edit_project_details',
            'can_view_all_teams', 'can_view_all_users',
            'view_logentry', # Audit logs
            # Financials (Read-Only usually, or Full)
            'view_invoices', 'view_subscription_plan', 'can_view_all_invoices',
            # User Management (High level)
            'add_user', 'change_user', 'can_invite_users'
        ]

     

        # Define the roles map
        roles_config = {
            'TESTER': TESTER_PERMS,
            'DEVELOPER': DEVELOPER_PERMS,
            'SCRUM_MASTER': SCRUM_MASTER_PERMS,
            'MANAGER': MANAGER_PERMS,
            'OWNER': '__ALL_BUSINESS__' # Special flag
        }

        for role_name, perms_config in roles_config.items():
            # Get or Create the Group (Idempotent)
            group, created = Group.objects.get_or_create(name=role_name)
            
            if created:
                self.stdout.write(f"  [+] Created group: {role_name}")
            else:
                self.stdout.write(f"  [*] Found existing group: {role_name}")

            # Resolve Permissions
            permissions_to_assign = []
            
            if perms_config == '__ALL_BUSINESS__':
                # OWNER LOGIC: Give all permissions except dangerous system internals
                # We exclude 'admin', 'contenttypes', and 'sessions' to prevent system breakage
                permissions_to_assign = Permission.objects.exclude(
                    content_type__app_label__in=['admin', 'contenttypes', 'sessions']
                )
                self.stdout.write(f"      -> Assigning ALL business permissions ({permissions_to_assign.count()} total)")
            
            else:
                # STANDARD ROLE LOGIC: Filter by codename list
                permissions_to_assign = Permission.objects.filter(codename__in=perms_config)
                
                # Validation: Check if we missed any permissions (Typo check)
                found_codenames = set(permissions_to_assign.values_list('codename', flat=True))
                requested_codenames = set(perms_config)
                missing = requested_codenames - found_codenames
                
                if missing:
                    self.stdout.write(self.style.WARNING(f"      [!] WARNING: These permissions were not found in DB: {missing}"))
                
                self.stdout.write(f"      -> Assigning {permissions_to_assign.count()} permissions")

            # Bulk Assign
            # We use set() to replace existing perms to ensure the state matches our config exactly
            group.permissions.set(permissions_to_assign)

        self.stdout.write(self.style.SUCCESS("\nSUCCESS: All roles and default permissions have been enforced."))