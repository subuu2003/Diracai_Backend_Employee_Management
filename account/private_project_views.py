from django.utils import timezone
from django.db.models import Q
from django.db import transaction
from django.conf import settings
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser, FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from account.authentication import QuietJWTAuthentication, CookieJWTAuthentication
from account.employee_models import (
    EmployeeProfile,
    PrivateProjectPlan,
    PrivateProjectAssignment,
    PrivateProjectDailyUpdate,
    PrivateProjectTicketAssignment,
    CurrentProjectPlan,
    CurrentProjectTicketAssignment,
)
from account.employee_serializers import (
    PrivateProjectPlanSerializer,
    PrivateProjectAssignmentSerializer,
    PrivateProjectDailyUpdateSerializer,
    CurrentProjectPlanSerializer,
)
from account.models import Project
from account.pagination import DefaultPageNumberPagination, wants_pagination
from account.permissions import CanAccessPrivateProject


def _is_admin(user):
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False) or getattr(user, "is_admin", False))
    )


def _can_read_project(user, project):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if _is_admin(user):
        return True
    if getattr(project, "project_manager_id", None) == getattr(user, "id", None):
        return True
    employee = getattr(user, "employee_profile", None)
    if not employee:
        return False
    if getattr(employee, "private_project_id", None) == getattr(project, "id", None):
        return True
    try:
        private_plan = getattr(project, "private_project_plan", None)
        if private_plan and private_plan.assignments.filter(employee=employee).exists():
            return True
        if private_plan:
            if private_plan.assignments.filter(employee=employee).exists():
                return True
            if private_plan.ticket_assignments.filter(employee=employee).exists():
                return True
    except Exception:
        pass
    return False


def _can_write_project(user, project):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if _is_admin(user):
        return True
    if getattr(project, "project_manager_id", None) == getattr(user, "id", None):
        return True
    employee = getattr(user, "employee_profile", None)
    if not employee:
        return False
    membership = getattr(project, "memberships", None)
    if membership is None:
        return False
    m = membership.filter(employee=employee, is_active=True).first()
    if not m:
        return False
    return getattr(m, "role", None) in {"pm", "lead"}


def _project_queryset_for_user(user):
    qs = Project.objects.select_related("project_manager").filter(private_project_plan__isnull=False)
    if not user or not getattr(user, "is_authenticated", False):
        if settings.DEBUG:
            return qs.distinct()
        return Project.objects.none()
    if _is_admin(user):
        return qs.distinct()
    employee = getattr(user, "employee_profile", None)
    q = Q(project_manager=user)
    if employee:
        private_project_id = getattr(employee, "private_project_id", None)
        if private_project_id:
            q = q | Q(pk=private_project_id)
        q = q | Q(private_project_plan__assignments__employee=employee)
        q = q | Q(private_project_plan__ticket_assignments__employee=employee)
    return qs.filter(q).distinct()


def _private_permissions(request):
    method = getattr(request, "method", "").upper()
    if method == "OPTIONS":
        return [AllowAny()]
    if settings.DEBUG and method in {"GET", "HEAD"}:
        return [AllowAny()]
    return [CanAccessPrivateProject()]


def _project_by_pk(pk):
    try:
        return Project.objects.select_related("project_manager", "current_project_plan", "private_project_plan").get(pk=pk)
    except Exception:
        return None


def _clean_private_plan_write_payload(plan_payload, project):
    """
    Frontends sometimes send extra keys (status, ticket_assignments, id, etc).
    DRF serializers reject unknown fields, so only pass writable plan fields.
    """
    raw = plan_payload if isinstance(plan_payload, dict) else {}

    # Accept common alias keys from frontends.
    project_name = raw.get("project_name") or raw.get("title") or raw.get("name") or ""
    project_description = raw.get("project_description") or raw.get("description") or raw.get("details") or ""

    cleaned = {
        "project": getattr(project, "id", None),
        "start_date": raw.get("start_date") or None,
        "end_date": raw.get("end_date") or None,
        "timeline": raw.get("timeline") or "",
        "project_name": project_name,
        "project_description": project_description,
    }

    # Drop empty strings for date fields (DRF DateField doesn't accept "").
    if cleaned["start_date"] in ("", "null"):
        cleaned["start_date"] = None
    if cleaned["end_date"] in ("", "null"):
        cleaned["end_date"] = None

    return cleaned


def _clean_current_plan_write_payload(plan_payload, project):
    raw = plan_payload if isinstance(plan_payload, dict) else {}

    project_name = raw.get("project_name") or raw.get("title") or raw.get("name") or ""
    project_description = raw.get("project_description") or raw.get("description") or raw.get("details") or ""

    cleaned = {
        "project": getattr(project, "id", None),
        "start_date": raw.get("start_date") or None,
        "end_date": raw.get("end_date") or None,
        "timeline": raw.get("timeline") or "",
        "project_name": project_name,
        "project_description": project_description,
    }
    if cleaned["start_date"] in ("", "null"):
        cleaned["start_date"] = None
    if cleaned["end_date"] in ("", "null"):
        cleaned["end_date"] = None

    # Pass through nested lists only if they look like lists.
    assignments_payload = raw.get("assignments")
    if not isinstance(assignments_payload, list):
        assignments_payload = raw.get("employees")
    if isinstance(assignments_payload, list):
        cleaned["assignments"] = assignments_payload

    ticket_payload = raw.get("ticket_assignments")
    if isinstance(ticket_payload, list):
        cleaned["ticket_assignments"] = ticket_payload

    return cleaned


def _sync_employee_private_project(employee, project):
    if not employee:
        return
    project_id = getattr(project, "id", None)
    if not project_id:
        return
    if getattr(employee, "private_project_id", None) == project_id:
        return
    employee.private_project = project
    employee.save(update_fields=["private_project", "updated_at"])


def _refresh_employee_private_project(employee):
    if not employee:
        return
    next_assignment = (
        PrivateProjectAssignment.objects.select_related("plan__project")
        .filter(employee=employee)
        .order_by("-id")
        .first()
    )
    next_project = getattr(getattr(next_assignment, "plan", None), "project", None)
    next_project_id = getattr(next_project, "id", None)
    current_project_id = getattr(employee, "private_project_id", None)
    if next_project_id:
        if current_project_id != next_project_id:
            employee.private_project = next_project
            employee.save(update_fields=["private_project", "updated_at"])
        return
    if current_project_id is not None:
        employee.private_project = None
        employee.save(update_fields=["private_project", "updated_at"])


def _sync_project_status_from_payload(project, payload, plan_payload=None):
    if not project:
        return
    status_candidate = None
    if isinstance(plan_payload, dict):
        status_candidate = plan_payload.get("status")
    if status_candidate is None and isinstance(payload, dict):
        status_candidate = payload.get("status")
    if status_candidate is not None:
        s_val = str(status_candidate).strip().lower()
        if s_val in {"active", "in_progress", "in-progress"}:
            s_val = "ongoing"
        elif s_val in {"on_hold", "on-hold", "paused"}:
            s_val = "planned"
        if s_val in {"planned", "ongoing", "completed"}:
            if getattr(project, "status", None) != s_val:
                project.status = s_val
                project.save(update_fields=["status"])


def _apply_private_assignments(plan, payload, request):
    assignments_payload = payload.get("assignments")
    assignments_payload = payload.get("employees", assignments_payload)
    if assignments_payload is None:
        return
    if not isinstance(assignments_payload, list):
        raise ValidationError({"assignments": "Expected a list"})

    keep_ids = set()
    for row in assignments_payload:
        if not isinstance(row, dict):
            raise ValidationError({"assignments": "Each item must be an object"})

        row_data = dict(row)
        employee_code = str(row_data.get("employee_id") or "").strip()
        # Drop read-only/nested values that can trigger writable-nested save errors.
        row_data.pop("id", None)
        row_data.pop("name", None)
        row_data.pop("employee_id", None)
        row_data.pop("daily_updates", None)
        row_data.pop("dailyUpdates", None)
        employee_value = row_data.get("employee")
        if employee_value in (None, "", "null"):
            # use original employee_id from incoming row as fallback
            if employee_code:
                employee_obj = EmployeeProfile.objects.filter(employee_id=employee_code).first()
                if not employee_obj:
                    raise ValidationError({"assignments": f"Invalid employee_id: {employee_code}"})
                row_data["employee"] = employee_obj.id

        employee_value = row_data.get("employee")
        if employee_value in (None, "", "null"):
            raise ValidationError({"assignments": "employee is required for each item"})

        try:
            employee_pk = int(str(employee_value).strip())
        except Exception:
            raise ValidationError({"assignments": f"Invalid employee: {employee_value}"})

        instance = PrivateProjectAssignment.objects.filter(plan=plan, employee_id=employee_pk).first()
        serializer = PrivateProjectAssignmentSerializer(
            instance,
            data=row_data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        assignment = serializer.save(plan=plan)
        if not assignment.designation:
            assignment.designation = getattr(assignment.employee, "designation", "") or ""
            assignment.save(update_fields=["designation"])
        _sync_employee_private_project(getattr(assignment, "employee", None), plan.project)
        keep_ids.add(assignment.id)

    stale_qs = PrivateProjectAssignment.objects.filter(plan=plan)
    if keep_ids:
        stale_qs = stale_qs.exclude(id__in=keep_ids)
    stale_employee_ids = list(stale_qs.values_list("employee_id", flat=True))
    stale_qs.delete()
    for employee_id in stale_employee_ids:
        employee_obj = EmployeeProfile.objects.filter(pk=employee_id).first()
        _refresh_employee_private_project(employee_obj)



def _private_project_payload(project, request, *, summary=False):
    plan = getattr(project, "private_project_plan", None) or getattr(project, "current_project_plan", None)
    if isinstance(plan, CurrentProjectPlan):
        plan_data = CurrentProjectPlanSerializer(plan, context={"request": request}).data
    else:
        plan_data = PrivateProjectPlanSerializer(plan, context={"request": request}).data if plan else None

    assigned_ids = [a.employee_id for a in getattr(plan, "assignments", []).all()] if plan else []
    assigned_codes = [a.employee.employee_id for a in getattr(plan, "assignments", []).all() if getattr(a, "employee", None)] if plan else []
    assigned_ids_set = set()
    assigned_codes_set = set()
    if plan:
        for a in getattr(plan, "assignments", []).all():
            if getattr(a, "employee_id", None):
                assigned_ids_set.add(a.employee_id)
            if getattr(a, "employee", None) and getattr(a.employee, "employee_id", None):
                assigned_codes_set.add(a.employee.employee_id)
        for ta in getattr(plan, "ticket_assignments", []).all():
            if getattr(ta, "employee_id", None):
                assigned_ids_set.add(ta.employee_id)
            if getattr(ta, "employee", None) and getattr(ta.employee, "employee_id", None):
                assigned_codes_set.add(ta.employee.employee_id)
    if project and hasattr(project, "employees"):
        for de in project.employees.all():
            assigned_ids_set.add(de.id)
            if getattr(de, "employee_id", None):
                assigned_codes_set.add(de.employee_id)

    assigned_ids = list(assigned_ids_set)
    assigned_codes = list(assigned_codes_set)

    project_tickets = []
    if isinstance(plan_data, dict) and plan_data.get("tickets"):
        project_tickets = plan_data.get("tickets") or []
    elif project is not None:
        pta_list = list(
            PrivateProjectTicketAssignment.objects.filter(plan__project=project).select_related("employee", "employee__user")
        )
        cta_list = list(
            CurrentProjectTicketAssignment.objects.filter(plan__project=project).select_related("employee", "employee__user")
        )
        all_bridge = pta_list + cta_list
        combined_ids = {ta.ticket_id for ta in all_bridge if ta.ticket_id}
        if combined_ids:
            bridge_emps_by_ticket = {}
            for ta in all_bridge:
                if ta.ticket_id and ta.employee:
                    bridge_emps_by_ticket.setdefault(ta.ticket_id, []).append(ta.employee)

            from account.employee_models import EmployeeTicket
            t_qs = (
                EmployeeTicket.objects.filter(pk__in=combined_ids)
                .select_related("assigned_to", "assigned_to__user", "employee", "employee__user")
                .prefetch_related("assignees", "assignees__user")
                .order_by("-updated_at", "-id")
            )
            for t in t_qs:
                emp_map = {}
                for e in bridge_emps_by_ticket.get(t.pk, []):
                    if e and e.id:
                        emp_map[e.id] = e
                for e in t.assignees.all():
                    if e and e.id:
                        emp_map[e.id] = e
                if t.assigned_to and t.assigned_to.id:
                    emp_map[t.assigned_to.id] = t.assigned_to

                assignees_list = list(emp_map.values())
                assigned_ids = list(emp_map.keys())

                project_tickets.append({
                    "id": t.pk,
                    "ticket_number": t.ticket_number or "",
                    "title": t.title or "",
                    "description": t.description or "",
                    "status": t.status or "",
                    "priority": t.priority or "",
                    "employee": {
                        "id": t.employee.id,
                        "name": _employee_label(t.employee),
                        "employee_code": getattr(t.employee, "employee_id", ""),
                    } if t.employee else None,
                    "assigned_to": {
                        "id": t.assigned_to.id,
                        "name": _employee_label(t.assigned_to),
                        "employee_code": getattr(t.assigned_to, "employee_id", ""),
                    } if t.assigned_to else None,
                    "assigned_employee_ids": assigned_ids,
                    "assignees": [
                        {
                            "id": e.id,
                            "name": _employee_label(e),
                            "employee_code": getattr(e, "employee_id", ""),
                        }
                        for e in assignees_list
                    ],
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else (t.created_at.isoformat() if t.created_at else None),
                })

    if summary and isinstance(plan_data, dict):
        assignments = plan_data.pop("assignments", None)
        plan_data.pop("employees", None)
        plan_data["assignments_count"] = len(assignments or []) if isinstance(assignments, list) else 0

    project_name = ""
    project_description = ""
    timeline = ""
    start_date = None
    end_date = None
    if isinstance(plan_data, dict):
        project_name = plan_data.get("project_name") or ""
        project_description = plan_data.get("project_description") or ""
        timeline = plan_data.get("timeline") or ""
        start_date = plan_data.get("start_date")
        end_date = plan_data.get("end_date")
    if start_date is None:
        start_date = getattr(project, "start_date", None)
    if end_date is None:
        end_date = getattr(project, "end_date", None)

    return {
        "id": project.id,
        "project_id": project.id,

        "project": {
            "id": project.id,
            "title": getattr(project, "title", "") or "",
            "description": getattr(project, "description", "") or "",
            "status": getattr(project, "status", "") or "",
            "timeline": getattr(project, "timeline", "") or "",
            "start_date": getattr(project, "start_date", None),
            "end_date": getattr(project, "end_date", None),
        },

        "title": project_name,
        "description": project_description,

        # IMPORTANT
        "status": getattr(project, "status", None),

        "timeline": timeline,
        "start_date": start_date,
        "end_date": end_date,
        "project_name": project_name,
        "project_description": project_description,
        "plan": plan_data,
        "tickets": project_tickets,
        "assigned_employee_ids": assigned_ids,
        "assigned_employee_codes": assigned_codes,
    }

class PrivateProjectsAPI(APIView):
    authentication_classes = [CookieJWTAuthentication, QuietJWTAuthentication, SessionAuthentication]
    permission_classes = [CanAccessPrivateProject]
    parser_classes = [JSONParser]

    def get_permissions(self):
        return _private_permissions(self.request)

    def get(self, request):
        qs = (
            _project_queryset_for_user(request.user)
            .select_related("private_project_plan")
            .prefetch_related(
                "private_project_plan__assignments",
                "private_project_plan__assignments__daily_updates",
            )
            .order_by("-updated_at")
        )
        employee = getattr(request.user, "employee_profile", None)
        if employee and not _is_admin(request.user):
            emp_q = (
                Q(private_project_plan__assignments__employee=employee)
                | Q(private_project_plan__ticket_assignments__employee=employee)
            )
            if employee.private_project_id:
                emp_q = emp_q | Q(pk=employee.private_project_id)
            qs = qs.filter(emp_q).distinct()

        # Admin filtering by specific employee
        target_emp_param = request.query_params.get("employee") or request.query_params.get("employee_id")
        if target_emp_param and _is_admin(request.user):
            target_emp = None
            param_str = str(target_emp_param).strip()
            if param_str.isdigit():
                target_emp = EmployeeProfile.objects.filter(pk=int(param_str)).first()
            if not target_emp:
                target_emp = EmployeeProfile.objects.filter(employee_id=param_str).first()
            if target_emp:
                target_q = (
                    Q(private_project_plan__assignments__employee=target_emp)
                    | Q(private_project_plan__ticket_assignments__employee=target_emp)
                )
                if target_emp.private_project_id:
                    target_q = target_q | Q(pk=target_emp.private_project_id)
                qs = qs.filter(target_q).distinct()
            else:
                qs = qs.none()
        items = []
        summary = request.query_params.get("summary") in ("1", "true", "yes")
        full = request.query_params.get("full") in ("1", "true", "yes")
        for project in qs:
            payload = _private_project_payload(project, request, summary=summary)
            assigned_ids = payload.get("assigned_employee_ids", [])
            assigned_codes = payload.get("assigned_employee_codes", [])
            if employee:
                payload["is_assigned_to_me"] = bool(employee.id in set(assigned_ids) or employee.employee_id in set(assigned_codes))
            items.append(payload)
        if wants_pagination(request):
            paginator = DefaultPageNumberPagination()
            page = paginator.paginate_queryset(items, request)
            return paginator.get_paginated_response(page)
        return Response(items, status=status.HTTP_200_OK)

    def post(self, request):
        if not _is_admin(request.user) and not getattr(request.user, "is_staff", False) and not getattr(request.user, "is_superuser", False):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data if isinstance(request.data, dict) else {}
        plan_payload = payload.get("plan") if isinstance(payload.get("plan"), dict) else payload
        project_id = plan_payload.get("project") or plan_payload.get("project_id") or payload.get("project") or payload.get("project_id")
        project = None
        if project_id not in (None, "", "null"):
            try:
                project = Project.objects.get(pk=int(str(project_id).strip()))
            except Exception:
                return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        # Allow creating a brand-new private project plan without going through `/api/projects/`.
        if project is None:
            title = (plan_payload.get("project_name") or plan_payload.get("title") or "").strip()
            if not title:
                return Response({"detail": "project_name is required"}, status=status.HTTP_400_BAD_REQUEST)
            description = (plan_payload.get("project_description") or plan_payload.get("description") or "").strip()
            status_value = (plan_payload.get("status") or "planned").strip().lower()
            if status_value not in {"planned", "ongoing", "completed"}:
                status_value = "planned"
            timeline = (plan_payload.get("timeline") or "").strip()
            start_date = plan_payload.get("start_date") or None
            end_date = plan_payload.get("end_date") or None
            if start_date in ("", "null"):
                start_date = None
            if end_date in ("", "null"):
                end_date = None

            with transaction.atomic():
                project = Project.objects.create(
                    title=title[:200],
                    description=description,
                    category="enterprise",
                    status=status_value,
                    timeline=timeline,
                    start_date=start_date,
                    end_date=end_date,
                    shortDescription=title[:200],
                    client="",
                )
                plan = PrivateProjectPlan.objects.create(project=project)

                data = _clean_private_plan_write_payload(plan_payload, project)
                serializer = PrivateProjectPlanSerializer(plan, data=data, partial=True, context={"request": request})
                serializer.is_valid(raise_exception=True)
                plan = serializer.save()
                _apply_private_assignments(plan, plan_payload if isinstance(plan_payload, dict) else {}, request)

            response_payload = _private_project_payload(project, request, summary=False)
            return Response(response_payload, status=status.HTTP_201_CREATED)

        if not _can_write_project(request.user, project):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        data = _clean_private_plan_write_payload(plan_payload, project)

        plan = PrivateProjectPlan.objects.filter(project=project).first()
        if plan is None:
            plan = PrivateProjectPlan.objects.create(project=project)
        serializer = PrivateProjectPlanSerializer(plan, data=data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        _sync_project_status_from_payload(project, payload, plan_payload)
        _apply_private_assignments(plan, plan_payload if isinstance(plan_payload, dict) else {}, request)
        plan = (
            PrivateProjectPlan.objects.select_related("project")
            .prefetch_related("assignments", "assignments__daily_updates")
            .filter(pk=plan.pk)
            .first()
            or plan
        )

        response_payload = _private_project_payload(project, request, summary=False)
        return Response(response_payload, status=status.HTTP_201_CREATED)


class PrivateProjectDetailAPI(APIView):
    authentication_classes = [
        CookieJWTAuthentication,
        QuietJWTAuthentication,
        SessionAuthentication,
    ]
    permission_classes = [CanAccessPrivateProject]
    parser_classes = [JSONParser]

    def get_permissions(self):
        return _private_permissions(self.request)

    def get(self, request, pk):
        """
        Get a private project by ID.

        Important:
        Do NOT use _project_queryset_for_user() here because that queryset
        requires private_project_plan__isnull=False.

        An existing Project may not have a PrivateProjectPlan yet.
        In that case, we create the plan automatically and return the
        existing project data.
        """

        # Fetch the project directly.
        project = (
            Project.objects
            .select_related(
                "project_manager",
                "private_project_plan",
            )
            .prefetch_related(
                "private_project_plan__assignments",
                "private_project_plan__assignments__daily_updates",
            )
            .filter(pk=pk)
            .first()
        )

        if project is None:
            return Response(
                {"detail": "Not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ---------------------------------------------------------
        # Permission check
        # ---------------------------------------------------------
        if not (
            settings.DEBUG
            and not getattr(request.user, "is_authenticated", False)
        ):
            try:
                self.check_object_permissions(request, project)
            except Exception:
                if not _is_admin(request.user):
                    return Response(
                        {"detail": "Not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                raise

        # ---------------------------------------------------------
        # Get existing private project plan
        # ---------------------------------------------------------
        plan = getattr(project, "private_project_plan", None)

        # ---------------------------------------------------------
        # If no private plan exists, create one automatically
        # from the existing Project information.
        # ---------------------------------------------------------
        if plan is None:
            plan = PrivateProjectPlan.objects.create(
                project=project,
                start_date=project.start_date,
                end_date=project.end_date,
                timeline=getattr(project, "timeline", "") or "",
                project_name=getattr(project, "title", "") or "",
                project_description=getattr(
                    project,
                    "description",
                    "",
                ) or "",
            )

            # Refresh the project relationship after creating the plan.
            project = (
                Project.objects
                .select_related(
                    "project_manager",
                    "private_project_plan",
                )
                .prefetch_related(
                    "private_project_plan__assignments",
                    "private_project_plan__assignments__daily_updates",
                )
                .get(pk=project.pk)
            )

        # ---------------------------------------------------------
        # Return the same payload structure used by the list API
        # ---------------------------------------------------------
        response_payload = _private_project_payload(
            project,
            request,
            summary=False,
        )

        return Response(
            response_payload,
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        return self._save_plan(request, pk, partial=True)

    def put(self, request, pk):
        return self._save_plan(request, pk, partial=False)

    def delete(self, request, pk):
        """
        Delete the private project plan.

        The underlying Project is NOT deleted.
        """

        # Do not use _project_queryset_for_user() here because the
        # project may not have a private plan.
        project = (
            Project.objects
            .select_related(
                "project_manager",
                "private_project_plan",
            )
            .filter(pk=pk)
            .first()
        )

        if project is None:
            return Response(
                {"detail": "Not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not _is_admin(request.user):
            return Response(
                {"detail": "Forbidden"},
                status=status.HTTP_403_FORBIDDEN,
            )

        plan = PrivateProjectPlan.objects.filter(
            project=project
        ).first()

        if plan is None:
            return Response(
                status=status.HTTP_204_NO_CONTENT
            )

        # Save employees affected by this private project before
        # deleting the plan.
        assigned_employee_ids = list(
            plan.assignments.values_list(
                "employee_id",
                flat=True,
            )
        )

        linked_employee_ids = list(
            EmployeeProfile.objects
            .filter(private_project_id=project.id)
            .values_list("id", flat=True)
        )

        affected_employee_ids = {
            int(employee_id)
            for employee_id in [
                *assigned_employee_ids,
                *linked_employee_ids,
            ]
            if employee_id is not None
        }

        # Delete only the private project plan.
        # The original Project remains available.
        plan.delete()

        # Remove direct private-project links.
        EmployeeProfile.objects.filter(
            private_project_id=project.id
        ).update(
            private_project=None,
            updated_at=timezone.now(),
        )

        # Restore another private project if the employee has one.
        for employee_id in affected_employee_ids:
            employee_obj = EmployeeProfile.objects.filter(
                pk=employee_id
            ).first()

            _refresh_employee_private_project(employee_obj)

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )

    def _save_plan(self, request, pk, partial):
        """
        Create/update the PrivateProjectPlan for an existing Project.
        """

        # ---------------------------------------------------------
        # Fetch project directly.
        # ---------------------------------------------------------
        project = (
            Project.objects
            .select_related(
                "project_manager",
                "private_project_plan",
            )
            .filter(pk=pk)
            .first()
        )

        if project is None:
            return Response(
                {"detail": "Not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ---------------------------------------------------------
        # Only admin can edit private project plans.
        # ---------------------------------------------------------
        if not _is_admin(request.user):
            return Response(
                {"detail": "Forbidden"},
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = (
            request.data
            if isinstance(request.data, dict)
            else {}
        )

        plan_payload = (
            payload.get("plan")
            if isinstance(payload.get("plan"), dict)
            else payload
        )

        # ---------------------------------------------------------
        # Find existing plan.
        # If it doesn't exist, create it from the Project.
        # ---------------------------------------------------------
        plan = PrivateProjectPlan.objects.filter(
            project=project
        ).first()

        if plan is None:
            plan = PrivateProjectPlan.objects.create(
                project=project,
                start_date=project.start_date,
                end_date=project.end_date,
                timeline=getattr(project, "timeline", "") or "",
                project_name=getattr(project, "title", "") or "",
                project_description=getattr(
                    project,
                    "description",
                    "",
                ) or "",
            )

        # ---------------------------------------------------------
        # Clean incoming plan data.
        # ---------------------------------------------------------
        data = _clean_private_plan_write_payload(
            plan_payload,
            project,
        )

        # ---------------------------------------------------------
        # Update the private plan.
        # ---------------------------------------------------------
        serializer = PrivateProjectPlanSerializer(
            plan,
            data=data,
            partial=partial,
            context={"request": request},
        )

        serializer.is_valid(raise_exception=True)

        plan = serializer.save()
        _sync_project_status_from_payload(project, payload, plan_payload)

        # ---------------------------------------------------------
        # Update employee assignments.
        # ---------------------------------------------------------
        _apply_private_assignments(
            plan,
            plan_payload
            if isinstance(plan_payload, dict)
            else {},
            request,
        )

        # ---------------------------------------------------------
        # Reload plan with assignments and daily updates.
        # ---------------------------------------------------------
        plan = (
            PrivateProjectPlan.objects
            .select_related("project")
            .prefetch_related(
                "assignments",
                "assignments__daily_updates",
                "ticket_assignments",
            )
            .filter(pk=plan.pk)
            .first()
            or plan
        )

        # ---------------------------------------------------------
        # Return the same payload structure expected by frontend.
        # ---------------------------------------------------------
        response_payload = _private_project_payload(
            project,
            request,
            summary=False,
        )

        return Response(
            response_payload,
            status=status.HTTP_200_OK,
        )

class PrivateProjectPlanAPI(APIView):
    authentication_classes = [CookieJWTAuthentication, QuietJWTAuthentication, SessionAuthentication]
    permission_classes = [CanAccessPrivateProject]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_permissions(self):
        return _private_permissions(self.request)

    def get(self, request, pk):
        project = _project_by_pk(pk)
        if project is None:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not (settings.DEBUG and not getattr(request.user, "is_authenticated", False)):
            try:
                self.check_object_permissions(request, project)
            except Exception:
                if not _is_admin(request.user):
                    return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
                raise
        plan = getattr(project, "current_project_plan", None) or getattr(project, "private_project_plan", None)
        if plan is None:
            return Response({"detail": "Plan not created"}, status=status.HTTP_404_NOT_FOUND)
        if isinstance(plan, CurrentProjectPlan):
            return Response(CurrentProjectPlanSerializer(plan, context={"request": request}).data, status=status.HTTP_200_OK)
        return Response(PrivateProjectPlanSerializer(plan, context={"request": request}).data, status=status.HTTP_200_OK)

    def post(self, request, pk):
        project = _project_by_pk(pk)
        if project is None:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        existing = getattr(project, "current_project_plan", None) or getattr(project, "private_project_plan", None)
        if existing is not None:
            if isinstance(existing, CurrentProjectPlan):
                return Response(CurrentProjectPlanSerializer(existing, context={"request": request}).data, status=status.HTTP_200_OK)
            return Response(PrivateProjectPlanSerializer(existing, context={"request": request}).data, status=status.HTTP_200_OK)

        plan = PrivateProjectPlan.objects.create(
            project=project,
            start_date=project.start_date,
            end_date=project.end_date,
            timeline=getattr(project, "timeline", "") or "",
            project_name=project.title,
            project_description=project.description or "",
        )
        return Response(PrivateProjectPlanSerializer(plan, context={"request": request}).data, status=status.HTTP_201_CREATED)

    def patch(self, request, pk):
        project = _project_by_pk(pk)
        if project is None:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        incoming = request.data if isinstance(request.data, dict) else {}

        current_plan = getattr(project, "current_project_plan", None)
        if current_plan is not None:
            data = _clean_current_plan_write_payload(incoming, project)
            serializer = CurrentProjectPlanSerializer(current_plan, data=data, partial=True, context={"request": request})
            serializer.is_valid(raise_exception=True)
            current_plan = serializer.save()
            return Response(CurrentProjectPlanSerializer(current_plan, context={"request": request}).data, status=status.HTTP_200_OK)

        plan = PrivateProjectPlan.objects.filter(project=project).first()
        if plan is None:
            return Response({"detail": "Plan not created"}, status=status.HTTP_404_NOT_FOUND)
        data = _clean_private_plan_write_payload(incoming, project)
        serializer = PrivateProjectPlanSerializer(plan, data=data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        plan = serializer.save()
        _sync_project_status_from_payload(project, incoming)
        _apply_private_assignments(plan, incoming, request)
        return Response(PrivateProjectPlanSerializer(plan, context={"request": request}).data, status=status.HTTP_200_OK)


class PrivateProjectPlanAssignmentsAPI(APIView):
    authentication_classes = [CookieJWTAuthentication, QuietJWTAuthentication, SessionAuthentication]
    permission_classes = [CanAccessPrivateProject]
    parser_classes = [JSONParser]

    def get_permissions(self):
        return _private_permissions(self.request)

    def post(self, request, pk):
        project = _project_by_pk(pk)
        if project is None:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        plan = PrivateProjectPlan.objects.filter(project=project).first()
        if plan is None:
            return Response({"detail": "Plan not created"}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        employee_id = payload.get("employee")
        if employee_id in (None, "", "null"):
            return Response({"detail": "Invalid payload"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            employee_obj = getattr(request.user, "employee_profile", None)
            if employee_obj and str(employee_obj.id) == str(employee_id):
                employee_obj = employee_obj
            else:
                employee_obj = EmployeeProfile.objects.get(pk=int(str(employee_id).strip()))
        except Exception:
            return Response({"detail": "Invalid employee"}, status=status.HTTP_400_BAD_REQUEST)

        assignment, _ = PrivateProjectAssignment.objects.get_or_create(plan=plan, employee=employee_obj)
        if not assignment.designation:
            assignment.designation = getattr(employee_obj, "designation", "") or ""
        for f in ("designation", "start_date", "end_date", "work", "status", "admin_comment", "employee_comment"):
            if f in payload:
                setattr(assignment, f, payload.get(f))
        assignment.save()
        _sync_employee_private_project(employee_obj, project)

        return Response(PrivateProjectAssignmentSerializer(assignment, context={"request": request}).data, status=status.HTTP_201_CREATED)


class PrivateProjectPlanAssignmentAPI(APIView):
    authentication_classes = [CookieJWTAuthentication, QuietJWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def get_permissions(self):
        if getattr(self.request, "method", "").upper() == "OPTIONS":
            return [AllowAny()]
        return [IsAuthenticated()]

    def patch(self, request, pk, assignment_id):
        project = _project_by_pk(pk)
        if project is None:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        plan = PrivateProjectPlan.objects.filter(project=project).first()
        if plan is None:
            return Response({"detail": "Plan not created"}, status=status.HTTP_404_NOT_FOUND)
        assignment = PrivateProjectAssignment.objects.filter(plan=plan, pk=assignment_id).first()
        if assignment is None:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data if isinstance(request.data, dict) else {}
        if not _is_admin(request.user):
            employee = getattr(getattr(request, "user", None), "employee_profile", None)
            if not employee or assignment.employee_id != getattr(employee, "id", None):
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            allowed = {"employee_comment"}
            for k in list(payload.keys()):
                if k not in allowed:
                    payload.pop(k, None)

        for f in ("designation", "start_date", "end_date", "work", "status", "admin_comment", "employee_comment"):
            if f in payload:
                setattr(assignment, f, payload.get(f))
        assignment.save()
        return Response(PrivateProjectAssignmentSerializer(assignment, context={"request": request}).data, status=status.HTTP_200_OK)

    def delete(self, request, pk, assignment_id):
        project = _project_by_pk(pk)
        if project is None:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        plan = PrivateProjectPlan.objects.filter(project=project).first()
        if plan is None:
            return Response({"detail": "Plan not created"}, status=status.HTTP_404_NOT_FOUND)
        assignment = PrivateProjectAssignment.objects.filter(plan=plan, pk=assignment_id).first()
        if assignment is None:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        employee_obj = getattr(assignment, "employee", None)
        assignment.delete()
        _refresh_employee_private_project(employee_obj)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProjectTicketsAPI(APIView):
    """
    GET /api/private-projects/<pk>/tickets/

    Returns ONLY the EmployeeTickets linked to this specific project through
    the existing bridge models:
      - PrivateProjectTicketAssignment  (for private-project plans)
      - CurrentProjectTicketAssignment  (for current-project plans)

    Ticket fields returned: id, ticket_number, title, status, priority,
    assignees (list of {id, name, employee_code}).

    Both private and current project flows are handled transparently.
    """

    authentication_classes = [CookieJWTAuthentication, QuietJWTAuthentication, SessionAuthentication]
    permission_classes = [CanAccessPrivateProject]

    def get_permissions(self):
        return _private_permissions(self.request)

    def get(self, request, pk):
        project = _project_by_pk(pk)
        if project is None:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        # Collect ticket IDs and bridge assignments from both bridge tables (no new FK on EmployeeTicket).
        private_assignments = list(
            PrivateProjectTicketAssignment.objects
            .filter(plan__project=project)
            .select_related("employee", "employee__user")
        )
        current_assignments = list(
            CurrentProjectTicketAssignment.objects
            .filter(plan__project=project)
            .select_related("employee", "employee__user")
        )
        all_assignments = private_assignments + current_assignments
        all_ticket_ids = {ta.ticket_id for ta in all_assignments if ta.ticket_id}

        if not all_ticket_ids:
            return Response([], status=status.HTTP_200_OK)

        bridge_emps_by_ticket = {}
        for ta in all_assignments:
            if ta.ticket_id and ta.employee:
                bridge_emps_by_ticket.setdefault(ta.ticket_id, []).append(ta.employee)

        from account.employee_models import EmployeeTicket
        tickets = (
            EmployeeTicket.objects
            .filter(pk__in=all_ticket_ids)
            .select_related("assigned_to", "assigned_to__user", "employee", "employee__user")
            .prefetch_related("assignees", "assignees__user")
            .order_by("-updated_at", "-id")
        )

        # Support optional employee filtering
        employee_param = request.query_params.get("employee") or request.query_params.get("employee_id")
        target_emp_id = None
        if employee_param:
            raw_param = str(employee_param).strip().lower()
            if raw_param == "me":
                ep = getattr(request.user, "employee_profile", None)
                if ep:
                    target_emp_id = ep.id
            else:
                try:
                    target_emp_id = int(raw_param)
                except (ValueError, TypeError):
                    pass

        def _employee_label(ep):
            if ep is None:
                return ""
            u = getattr(ep, "user", None)
            first = getattr(u, "firstname", "") or getattr(u, "first_name", "") or ""
            last = getattr(u, "lastname", "") or getattr(u, "last_name", "") or ""
            full = f"{first} {last}".strip()
            return full or getattr(u, "username", "") or getattr(u, "email", "") or f"Employee #{ep.id}"

        def _emp_info(ep):
            if not ep:
                return None
            return {
                "id": ep.id,
                "name": _employee_label(ep),
                "employee_code": getattr(ep, "employee_id", ""),
            }

        data = []
        for t in tickets:
            emp_map = {}
            for e in bridge_emps_by_ticket.get(t.pk, []):
                if e and e.id:
                    emp_map[e.id] = e
            for e in t.assignees.all():
                if e and e.id:
                    emp_map[e.id] = e
            if t.assigned_to and t.assigned_to.id:
                emp_map[t.assigned_to.id] = t.assigned_to

            assignees_list = list(emp_map.values())
            assigned_ids = list(emp_map.keys())

            if target_emp_id is not None:
                is_linked = (
                    target_emp_id in assigned_ids
                    or (t.employee_id is not None and t.employee_id == target_emp_id)
                )
                if not is_linked:
                    continue

            data.append({
                "id": t.pk,
                "ticket_number": t.ticket_number or "",
                "title": t.title or "",
                "description": t.description or "",
                "status": t.status or "",
                "priority": t.priority or "",
                "employee": _emp_info(t.employee),
                "assigned_to": _emp_info(t.assigned_to),
                "assigned_employee_ids": assigned_ids,
                "assignees": [
                    {
                        "id": e.id,
                        "name": _employee_label(e),
                        "employee_code": getattr(e, "employee_id", ""),
                    }
                    for e in assignees_list
                ],
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else (t.created_at.isoformat() if t.created_at else None),
            })

        return Response(data, status=status.HTTP_200_OK)


class PrivateProjectDailyUpdatesAPI(APIView):
    authentication_classes = [CookieJWTAuthentication, QuietJWTAuthentication, SessionAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def get_permissions(self):
        if getattr(self.request, "method", "").upper() == "OPTIONS":
            return [AllowAny()]
        return [IsAuthenticated()]

    def post(self, request, pk, assignment_id):
        project = _project_by_pk(pk)
        if project is None:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        plan = PrivateProjectPlan.objects.filter(project=project).first()
        if plan is None:
            return Response({"detail": "Plan not created"}, status=status.HTTP_404_NOT_FOUND)
        assignment = PrivateProjectAssignment.objects.filter(plan=plan, pk=assignment_id).first()
        if assignment is None:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if not _is_admin(request.user):
            employee = getattr(getattr(request, "user", None), "employee_profile", None)
            if not employee or assignment.employee_id != getattr(employee, "id", None):
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data if isinstance(request.data, dict) else {}
        text = (payload.get("text") or "").strip()
        date = payload.get("date")
        if not text or not date:
            return Response({"detail": "Invalid payload"}, status=status.HTTP_400_BAD_REQUEST)

        update = PrivateProjectDailyUpdate.objects.create(assignment=assignment, date=date, text=text)
        return Response(PrivateProjectDailyUpdateSerializer(update, context={"request": request}).data, status=status.HTTP_201_CREATED)
