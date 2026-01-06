from rest_framework import permissions
from django.core.exceptions import PermissionDenied
from project.models import ProjectMember
from user.models import User


class RBACPermission(permissions.BasePermission):
    """
    Generic permission class that checks for required permissions 
    based on the 'perms_map' defined in the ViewSet.
    """
    def has_permission(self, request, view):
        # 1. Allow Superusers and Project Owners to bypass RBAC checks completely
        if request.user.is_superuser:
            return True
        if getattr(request.user, 'role', '') == 'OWNER':
            return True

        # 2. Get the permission map from the ViewSet
        perms_map = getattr(view, 'perms_map', {})

        # 3. Determine the current action
        if hasattr(view, 'action'):
            # ViewSets have an 'action' attribute (list, create, retrieve, etc.)
            action = view.action
        else:
            # GenericAPIViews (CreateAPIView, etc.) rely on HTTP methods
            method_mapper = {
                'GET': 'retrieve', # Default assumption, can be overridden
                'POST': 'create',
                'PUT': 'update',
                'PATCH': 'partial_update',
                'DELETE': 'destroy'
            }
            action = method_mapper.get(request.method)

        # [FIXED LINE] Use the local 'action' variable we just determined.
        # Do NOT use 'view.action' here, because APIViews don't have it.
        required_perm = perms_map.get(action)

        # 4. If no specific permission is required for this action, allow it
        if not required_perm:
            return True

        # 5. The Core Check: Does the user (via their Role/Group) have this permission?
        if request.user.has_perm(required_perm):
            return True
        
        return False

    def has_object_permission(self, request, view, obj):
        # 1. Project Membership Check
        project = getattr(obj, 'project', None)
        if project:
            is_member = ProjectMember.objects.filter(user=request.user, project=project).exists()
            is_owner = project.owner == request.user
            if not (is_member or is_owner or request.user.is_superuser):
                return False 

        # 2. Proceed with standard RBAC check
        return True

# ... [Keep your helper functions and other classes below as they were] ...
def check_project_permission(user, project, allowed_roles=None):
    # (Keep your existing implementation)
    membership = ProjectMember.objects.filter(user=user, project=project).first()
    if not membership:
        raise PermissionDenied("You are not a member of this project.")
    
    if allowed_roles is None:
        default_roles = ["OWNER", "PROJECT_MANAGER","SCRUM_MASTER"]
        if membership.role not in default_roles:
            raise PermissionDenied("You do not have permission to perform this action.")
    elif allowed_roles == []:
        return True
    elif allowed_roles and membership.role not in allowed_roles:
        raise PermissionDenied("You do not have the required role for this action.")
    return True

# ... [Keep IsOwnerOrAdmin, etc.] ...

# class RBACPermission(permissions.BasePermission):
#     """
#     Generic permission class that checks for required permissions 
#     based on the 'perms_map' defined in the ViewSet.
#     """
#     def has_permission(self, request, view):
#         # 1. Allow Superusers and Project Owners to bypass RBAC checks completely
#         # (Assuming your User model has a 'role' field or similar logic)
#         if request.user.is_superuser:
#             return True
#         if getattr(request.user, 'role', '') == 'OWNER':
#             return True

#         # 2. Get the permission map from the ViewSet
#         # This looks for a dictionary called 'perms_map' in your view
#         perms_map = getattr(view, 'perms_map', {})

#         # 3. Determine the required permission for the current action
#         # view.action is typically 'list', 'create', 'retrieve', 'update', 'destroy'
#         if hasattr(view, 'action'):
#             # ViewSets have an 'action' attribute (list, create, retrieve, etc.)
#             action = view.action
#         else:
#             # GenericAPIViews (CreateAPIView, etc.) rely on HTTP methods
#             method_mapper = {
#                 'GET': 'retrieve', # Default assumption, can be overridden
#                 'POST': 'create',
#                 'PUT': 'update',
#                 'PATCH': 'partial_update',
#                 'DELETE': 'destroy'
#             }
#             action = method_mapper.get(request.method)
#         required_perm = perms_map.get(view.action)

#         # 4. If no specific permission is required for this action, allow it
#         # (This lets you mix RBAC with standard IsAuthenticated views)
#         if not required_perm:
#             return True

#         # 5. The Core Check: Does the user (via their Role/Group) have this permission?
#         if request.user.has_perm(required_perm):
#             return True
        
#         return False
#     def has_object_permission(self, request, view, obj):
#         # This runs when accessing a specific task (GET /tasks/5/)
        
#         # 1. Project Membership Check
#         # Assuming 'obj' is a Task, it has a .project attribute
#         project = getattr(obj, 'project', None)
#         if project:
#             is_member = ProjectMember.objects.filter(user=request.user, project=project).exists()
#             is_owner = project.owner == request.user
#             if not (is_member or is_owner or request.user.is_superuser):
#                 return False  # Not even a member of this project!

#         # 2. Proceed with standard RBAC check
#         # (The view logic will handle the specific 'can_delete' check)
#         return True
def check_project_permission(user, project, allowed_roles=None):
    """Utility function to check if user has required role for a project."""
    membership = ProjectMember.objects.filter(user=user, project=project).first()

    # This part always runs, checking for basic membership.
    if not membership:
        raise PermissionDenied("You are not a member of this project.")

    # If allowed_roles is None, use the default restrictive roles.
    if allowed_roles is None:
        default_roles = ["OWNER", "PROJECT_MANAGER","SCRUM_MASTER"]
        if membership.role not in default_roles:
            raise PermissionDenied("You do not have permission to perform this action.")
    elif allowed_roles == []:
        return True
    # If allowed_roles is a non-empty list, check against it.
    elif allowed_roles and membership.role not in allowed_roles:
        raise PermissionDenied("You do not have the required role for this action.")
    return True

class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed to any request,
        # so we'll always allow GET, HEAD or OPTIONS requests.
        if request.method in permissions.SAFE_METHODS:
            return True

        # Write permissions are only allowed to the owner of the account or an admin.
        return obj == request.user or request.user.is_staff
 

class IsOwnerUser(permissions.BasePermission):
    """
    Custom permission to only allow users with the 'OWNER' role to access a view.
    """
    def has_permission(self, request, view):
        # Check if the user is authenticated and has the role of 'OWNER'
        return request.user and request.user.is_authenticated and request.user.role == User.Role.OWNER
    

class IsOwnerAdminOrManager(permissions.BasePermission):
    """
    Allows access only to Owners, Admins, or Managers.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.role in [
            User.Role.OWNER, 
            User.Role.ADMIN, 
            User.Role.MANAGER
        ]
    

class IsOwnerAdminOrScrumMaster(permissions.BasePermission):
    """
    Custom permission to only allow users with the global role of
    Owner, Admin, or Scrum Master.
    """
    message = "You do not have permission to create a team. Only Owners, Admins, and Scrum Masters are allowed."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if the user's role is one of the allowed roles [cite: models.py]
        return request.user.role in [
            User.Role.OWNER,
            User.Role.ADMIN,
            User.Role.SCRUM_MASTER
        ]
    


class IsOwnerAdminOrScrumMasterOrManager(permissions.BasePermission):
    """
    Custom permission to only allow users with the global role of
    Owner, Admin, or Scrum Master.
    """
    message = "You do not have permission to create a team. Only Owners, Admins, and Scrum Masters are allowed."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Check if the user's role is one of the allowed roles [cite: models.py]
        return request.user.role in [
            User.Role.OWNER,
            User.Role.ADMIN,
            User.Role.SCRUM_MASTER,
            User.Role.MANAGER
        ]

