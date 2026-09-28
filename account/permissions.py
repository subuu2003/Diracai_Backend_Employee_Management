from rest_framework.permissions import BasePermission, SAFE_METHODS

from account.employee_models import PrivateProjectAssignment
from account.employee_models import PrivateProjectAssignment, PrivateProjectTicketAssignment


class CanAccessPrivateProject(BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if request.method in SAFE_METHODS:
            return True
        return bool(getattr(user, "is_staff", False) or getattr(user, "is_superuser", False) or getattr(user, "is_admin", False))

    def has_object_permission(self, request, view, obj):
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False) or getattr(user, "is_admin", False):
            return True

        employee = getattr(user, "employee_profile", None)
        if not employee:
            return False

        project_id = getattr(obj, "project_id", None) or getattr(getattr(obj, "project", None), "id", None) or getattr(obj, "id", None)
        if not project_id:
            return False

        return PrivateProjectAssignment.objects.filter(plan__project_id=project_id, employee=employee).exists()
        if getattr(employee, "private_project_id", None) == project_id:
            return True

        if PrivateProjectAssignment.objects.filter(plan__project_id=project_id, employee=employee).exists():
            return True

        if PrivateProjectTicketAssignment.objects.filter(plan__project_id=project_id, employee=employee).exists():
            return True

        return False
