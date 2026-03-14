from datetime import date, timedelta
import mimetypes
import os

from django.contrib.auth import get_user_model
from django.conf import settings
from django.http import FileResponse
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser, JSONParser
from account.pagination import DefaultPageNumberPagination, wants_pagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authentication import SessionAuthentication
from rest_framework.renderers import JSONRenderer, BrowsableAPIRenderer
from django.core.files.uploadedfile import UploadedFile

from account.authentication import QuietJWTAuthentication

from account.employee_models import (
    EmployeeDocument,
    EmployeeProfile,
    LeaveRequest,
    OvertimeRequest,
    EmployeeTicket,
    EmployeeTicketAssignmentHistory,
    EmployeeTicketComment,
)
from account.models import Project
from account.employee_serializers import (
    EmployeeAdminSerializer,
    EmployeeAdminListSerializer,
    EmployeeDocumentSerializer,
    EmployeeProfileSerializer,
    PublicEmployeeSerializer,
    PublicEmployeeListSerializer,
    EmployeeTicketCommentSerializer,
    EmployeeTicketDetailSerializer,
    EmployeeTicketListSerializer,
    _employee_integrity_error_detail,
    _ticket_status_from_api,
    LeaveRequestSerializer,
    OvertimeRequestSerializer,
)


User = get_user_model()


class DebugForce200Mixin:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if getattr(self, "disable_force_200", False):
            return response
        if not getattr(settings, "DEBUG", False):
            return response
        status_code = getattr(response, "status_code", 200)
        if status_code < 400:
            return response
        if hasattr(response, "data"):
            payload = response.data
            response.data = {
                "success": False,
                "original_status": int(status_code),
                "error": payload,
            }
        response.status_code = status.HTTP_200_OK
        return response


def _is_admin(user):
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))

def _can_manage_projects(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False) or getattr(user, "is_admin", False):
        return True
    usertype = getattr(user, "usertype", None)
    name = getattr(usertype, "name", None)
    if isinstance(name, str) and name.strip().lower() in {"founder", "director"}:
        return True
    employee_profile = getattr(user, "employee_profile", None)
    designation = getattr(employee_profile, "designation", None)
    if isinstance(designation, str) and "project manager" in designation.strip().lower():
        return True
    return False

def _normalize_document_status(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    mapping = {
        "pending": "pending",
        "approved": "approved",
        "approve": "approved",
        "accepted": "approved",
        "verified": "verified",
        "verify": "verified",
        "active": "approved",
        "rejected": "rejected",
        "reject": "rejected",
        "declined": "rejected",
        "inactive": "rejected",
    }
    return mapping.get(text, value)

def _resolve_employee(param):
    if param in (None, ""):
        return None
    try:
        return EmployeeProfile.objects.select_related("user").get(pk=int(param))
    except (ValueError, TypeError, EmployeeProfile.DoesNotExist):
        pass
    try:
        return EmployeeProfile.objects.select_related("user").get(employee_id=str(param))
    except EmployeeProfile.DoesNotExist:
        return None


def _can_access_ticket(user, ticket):
    if not ticket:
        return False
    if _is_admin(user):
        return True
    if not user or not getattr(user, "is_authenticated", False):
        return False
    me = getattr(user, "employee_profile", None)
    if not me:
        return False
    if getattr(ticket, "employee_id", None) == me.id:
        return True
    if getattr(ticket, "assigned_to_id", None) == me.id:
        return True
    return False


class EmployeesAPI(DebugForce200Mixin, APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def _try_create_document(self, request, employee):
        file_value = request.data.get("document_file") or request.data.get("file")
        if not isinstance(file_value, UploadedFile):
            return None
        doc_payload = {
            "employee": employee.id,
            "title": request.data.get("document_title", request.data.get("title", "")),
            "description": request.data.get("document_description", request.data.get("description", "")),
            "document_type": request.data.get("document_type", ""),
            "file": file_value,
        }
        doc_serializer = EmployeeDocumentSerializer(data=doc_payload, context={"request": request})
        if not doc_serializer.is_valid():
            return Response(doc_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            doc_serializer.save()
        except OSError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_507_INSUFFICIENT_STORAGE)
        except Exception:
            return Response({"detail": "Document upload failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return None

    def get(self, request):
        qs = EmployeeProfile.objects.select_related("user").all()
        active_param = request.query_params.get("active", request.query_params.get("is_active"))
        can_take = request.query_params.get("can_take_tickets")
        if str(active_param).strip().lower() in {"1", "true", "yes"} or str(can_take).strip().lower() in {"1", "true", "yes"}:
            qs = qs.filter(status="active")
        include_documents = request.query_params.get("include_documents") in ("1", "true", "yes")
        full = request.query_params.get("full") in ("1", "true", "yes")
        want_full = include_documents or full

        if _is_admin(request.user):
            serializer_cls = EmployeeAdminSerializer if want_full else EmployeeAdminListSerializer
        else:
            serializer_cls = PublicEmployeeSerializer if want_full else PublicEmployeeListSerializer

        if request.query_params.get("nopaginate") not in ("1", "true", "yes"):
            paginator = DefaultPageNumberPagination()
            page = paginator.paginate_queryset(qs.order_by("-updated_at"), request)
            data = serializer_cls(page, many=True, context={"request": request}).data
            return paginator.get_paginated_response(data)

        return Response(
            serializer_cls(qs, many=True, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        name = request.data.get("name", "")
        password = request.data.get("password", None)
        login_id_value = (
            request.data.get("login_id")
            or request.data.get("loginId")
            or request.data.get("login")
            or request.data.get("username")
            or ""
        )
        current_project = request.data.get("private_project", request.data.get("private_project_id", None))
        current_project = request.data.get("current_project", request.data.get("current_project_id", current_project))

        email_value = (
            request.data.get("email")
            or request.data.get("gmail")
            or request.data.get("user_email")
            or request.data.get("userEmail")
            or ""
        )

        phone_value = (
            request.data.get("phone")
            or request.data.get("phoneno")
            or request.data.get("phoneNo")
            or request.data.get("mobile")
            or request.data.get("mobileNo")
            or ""
        )

        # Support admin UI that only sends `login_id` (email or phone).
        login_id_value = str(login_id_value).strip()
        if not (isinstance(email_value, str) and email_value.strip()) and login_id_value and "@" in login_id_value:
            email_value = login_id_value
        if not str(phone_value).strip() and login_id_value and "@" not in login_id_value:
            phone_value = login_id_value

        payload = {
            "phone": str(phone_value).strip(),
            "designation": request.data.get("designation", ""),
            "qualification": request.data.get("qualification", ""),
            "employment_type": request.data.get("employment_type", ""),
            "location": request.data.get("location", ""),
            "status": request.data.get("status", "active"),
            "private_project": current_project,
        }
        if isinstance(email_value, str) and email_value.strip():
            payload["email"] = email_value.strip()

        upload = request.data.get("profile_image") or request.data.get("profile_pic") or request.data.get("profilePic")
        if isinstance(upload, UploadedFile):
            payload["profile_image"] = upload

        serializer = EmployeeAdminSerializer(
            data=payload,
            context={"request": request, "name": name, "password": password},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_200_OK if settings.DEBUG else status.HTTP_400_BAD_REQUEST)
        try:
            employee = serializer.save()
        except ValidationError as exc:
            detail = getattr(exc, "detail", exc.args[0] if exc.args else {"detail": "Invalid employee data"})
            return Response(detail, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError as exc:
            return Response(_employee_integrity_error_detail(exc), status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            return Response(
                {"detail": f"Employee creation failed: {str(exc)}"} if settings.DEBUG else {"detail": "Employee creation failed"},
                status=status.HTTP_400_BAD_REQUEST if settings.DEBUG else status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        document_error = self._try_create_document(request, employee)
        if document_error is not None:
            return document_error
        return Response(EmployeeAdminSerializer(employee, context={"request": request}).data, status=status.HTTP_200_OK)


class EmployeeDetailAPI(DebugForce200Mixin, APIView):
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_object(self, pk):
        try:
            return EmployeeProfile.objects.select_related("user").get(pk=pk)
        except EmployeeProfile.DoesNotExist:
            return None

    def _try_create_document(self, request, employee):
        file_value = request.data.get("document_file") or request.data.get("file")
        if not isinstance(file_value, UploadedFile):
            return None
        doc_payload = {
            "employee": employee.id,
            "title": request.data.get("document_title", request.data.get("title", "")),
            "description": request.data.get("document_description", request.data.get("description", "")),
            "document_type": request.data.get("document_type", ""),
            "file": file_value,
        }
        doc_serializer = EmployeeDocumentSerializer(data=doc_payload, context={"request": request})
        if not doc_serializer.is_valid():
            return Response(doc_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            doc_serializer.save()
        except OSError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_507_INSUFFICIENT_STORAGE)
        except Exception:
            return Response({"detail": "Document upload failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return None

    def get(self, request, pk):
        employee = self.get_object(pk)
        if not employee:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if _is_admin(request.user):
            return Response(
                EmployeeAdminSerializer(employee, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )
        if hasattr(request.user, "employee_profile") and request.user.employee_profile.id == employee.id:
            return Response(
                EmployeeProfileSerializer(employee, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )
        return Response(
            PublicEmployeeSerializer(employee, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    def patch(self, request, pk):
        employee = self.get_object(pk)
        if not employee:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if _is_admin(request.user):
            name = request.data.get("name", None)
            password = request.data.get("password", None)

            payload = {}
            for field in ("phone", "designation", "qualification", "employment_type", "location", "status", "private_project", "current_project"):
                if field in request.data:
                    payload[field] = request.data.get(field)

            if "private_project_id" in request.data and "private_project" not in payload:
                payload["private_project"] = request.data.get("private_project_id")
            if "current_project_id" in request.data and "private_project" not in payload:
                payload["private_project"] = request.data.get("current_project_id")

            email_value = (
                request.data.get("email")
                or request.data.get("gmail")
                or request.data.get("user_email")
                or request.data.get("userEmail")
            )
            if email_value is not None:
                payload["email"] = email_value

            upload = request.data.get("profile_image") or request.data.get("profile_pic") or request.data.get("profilePic")
            if isinstance(upload, UploadedFile):
                payload["profile_image"] = upload

            serializer = EmployeeAdminSerializer(
                employee,
                data=payload,
                partial=True,
                context={"request": request, "name": name, "password": password},
            )
            try:
                serializer.is_valid(raise_exception=True)
                employee = serializer.save()
            except ValidationError as exc:
                return Response(getattr(exc, "detail", {"detail": "Invalid data"}), status=status.HTTP_400_BAD_REQUEST)
            except IntegrityError as exc:
                return Response(_employee_integrity_error_detail(exc), status=status.HTTP_400_BAD_REQUEST)
            except Exception as exc:
                return Response(
                    {"detail": f"Employee update failed: {str(exc)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            document_error = self._try_create_document(request, employee)
            if document_error is not None:
                return document_error
            return Response(EmployeeAdminSerializer(employee, context={"request": request}).data, status=status.HTTP_200_OK)

        if not hasattr(request.user, "employee_profile") or request.user.employee_profile.id != employee.id:
            if _can_manage_projects(request.user):
                if "private_project" in request.data or "private_project_id" in request.data or "current_project" in request.data or "current_project_id" in request.data:
                    project_value = request.data.get("private_project", request.data.get("private_project_id"))
                    project_value = request.data.get("current_project", request.data.get("current_project_id", project_value))
                    if project_value in (None, "", "null"):
                        employee.private_project = None
                        employee.save(update_fields=["private_project", "updated_at"])
                        return Response(
                            EmployeeAdminSerializer(employee, context={"request": request}).data
                            if _is_admin(request.user)
                            else EmployeeProfileSerializer(employee, context={"request": request}).data,
                            status=status.HTTP_200_OK,
                        )
                    try:
                        project_id = int(project_value)
                    except Exception:
                        return Response({"detail": "Invalid project id"}, status=status.HTTP_400_BAD_REQUEST)
                    try:
                        project = Project.objects.get(pk=project_id)
                    except Project.DoesNotExist:
                        return Response({"detail": "Project not found"}, status=status.HTTP_404_NOT_FOUND)
                    employee.private_project = project
                    employee.save(update_fields=["private_project", "updated_at"])
                    return Response(
                        EmployeeAdminSerializer(employee, context={"request": request}).data
                        if _is_admin(request.user)
                        else EmployeeProfileSerializer(employee, context={"request": request}).data,
                        status=status.HTTP_200_OK,
                    )
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        payload = {}
        for field in ("phone", "designation", "qualification", "employment_type", "location", "private_project", "current_project"):
            if field in request.data:
                payload[field] = request.data.get(field)
        if "private_project_id" in request.data and "private_project" not in payload:
            payload["private_project"] = request.data.get("private_project_id")
        if "current_project_id" in request.data and "private_project" not in payload:
            payload["private_project"] = request.data.get("current_project_id")

        upload = request.data.get("profile_image") or request.data.get("profile_pic") or request.data.get("profilePic")
        if isinstance(upload, UploadedFile):
            payload["profile_image"] = upload

        serializer = EmployeeAdminSerializer(
            employee,
            data=payload,
            partial=True,
            context={"request": request, "name": request.data.get("name", None), "password": request.data.get("password", None)},
        )
        serializer.is_valid(raise_exception=True)
        employee = serializer.save()
        document_error = self._try_create_document(request, employee)
        if document_error is not None:
            return document_error
        return Response(EmployeeProfileSerializer(employee, context={"request": request}).data, status=status.HTTP_200_OK)

    def post(self, request, pk):
        return self.patch(request, pk)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        if not _is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        employee = self.get_object(pk)
        if not employee:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        user = employee.user
        employee.delete()
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployeeDocumentFileAPI(DebugForce200Mixin, APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk, doc_id):
        employee = EmployeeProfile.objects.filter(pk=pk).first()
        if not employee:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        document = EmployeeDocument.objects.filter(pk=doc_id, employee=employee).first()
        if not document or not document.file:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        try:
            fh = document.file.open("rb")
        except Exception:
            return Response({"detail": "File not available"}, status=status.HTTP_404_NOT_FOUND)
        response = FileResponse(fh)
        content_type, _ = mimetypes.guess_type(document.file.name or "")
        response["Content-Type"] = content_type or "application/octet-stream"
        response["Content-Disposition"] = f'inline; filename="{os.path.basename(document.file.name)}"'
        return response


class LeaveRequestsAPI(DebugForce200Mixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee_param = request.query_params.get("employee")
        employee = _resolve_employee(employee_param)

        if _is_admin(request.user):
            qs = LeaveRequest.objects.select_related("employee", "employee__user").all()
            if employee:
                qs = qs.filter(employee=employee)
        else:
            if not hasattr(request.user, "employee_profile"):
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            if employee and employee.id != request.user.employee_profile.id:
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            qs = LeaveRequest.objects.select_related("employee", "employee__user").filter(employee=request.user.employee_profile)

        return Response(
            LeaveRequestSerializer(qs, many=True).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        if not hasattr(request.user, "employee_profile"):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        payload = dict(request.data)
        payload["employee"] = request.user.employee_profile.id
        serializer = LeaveRequestSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(LeaveRequestSerializer(obj).data, status=status.HTTP_201_CREATED)


class LeaveRequestDetailAPI(DebugForce200Mixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return LeaveRequest.objects.select_related("employee", "employee__user").get(pk=pk)
        except LeaveRequest.DoesNotExist:
            return None

    def patch(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if _is_admin(request.user):
            data = {}
            if "status" in request.data:
                data["status"] = request.data.get("status")
            serializer = LeaveRequestSerializer(obj, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            obj = serializer.save()
            return Response(LeaveRequestSerializer(obj).data, status=status.HTTP_200_OK)

        if not hasattr(request.user, "employee_profile") or obj.employee_id != request.user.employee_profile.id:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        data = {}
        if "status" in request.data and str(request.data.get("status")).lower() == "cancelled":
            if obj.status == "pending":
                data["status"] = "cancelled"
        for field in ("start_date", "end_date", "reason"):
            if field in request.data and obj.status == "pending":
                data[field] = request.data.get(field)

        if not data:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        serializer = LeaveRequestSerializer(obj, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(LeaveRequestSerializer(obj).data, status=status.HTTP_200_OK)

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if _is_admin(request.user) or (hasattr(request.user, "employee_profile") and obj.employee_id == request.user.employee_profile.id):
            return Response(LeaveRequestSerializer(obj).data, status=status.HTTP_200_OK)
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)


class OvertimeRequestsAPI(DebugForce200Mixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        employee_param = request.query_params.get("employee")
        employee = _resolve_employee(employee_param)

        if _is_admin(request.user):
            qs = OvertimeRequest.objects.select_related("employee", "employee__user").all()
            if employee:
                qs = qs.filter(employee=employee)
        else:
            if not hasattr(request.user, "employee_profile"):
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            if employee and employee.id != request.user.employee_profile.id:
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            qs = OvertimeRequest.objects.select_related("employee", "employee__user").filter(employee=request.user.employee_profile)

        return Response(
            OvertimeRequestSerializer(qs, many=True).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        if not hasattr(request.user, "employee_profile"):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        payload = dict(request.data)
        payload["employee"] = request.user.employee_profile.id
        serializer = OvertimeRequestSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(OvertimeRequestSerializer(obj).data, status=status.HTTP_201_CREATED)


class OvertimeRequestDetailAPI(DebugForce200Mixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        try:
            return OvertimeRequest.objects.select_related("employee", "employee__user").get(pk=pk)
        except OvertimeRequest.DoesNotExist:
            return None

    def patch(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if _is_admin(request.user):
            data = {}
            if "status" in request.data:
                data["status"] = request.data.get("status")
            serializer = OvertimeRequestSerializer(obj, data=data, partial=True)
            serializer.is_valid(raise_exception=True)
            obj = serializer.save()
            return Response(OvertimeRequestSerializer(obj).data, status=status.HTTP_200_OK)

        if not hasattr(request.user, "employee_profile") or obj.employee_id != request.user.employee_profile.id:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        data = {}
        if "status" in request.data and str(request.data.get("status")).lower() == "cancelled":
            if obj.status == "pending":
                data["status"] = "cancelled"
        for field in ("reason", "date", "hours"):
            if field in request.data and obj.status == "pending":
                data[field] = request.data.get(field)

        if not data:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        serializer = OvertimeRequestSerializer(obj, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(OvertimeRequestSerializer(obj).data, status=status.HTTP_200_OK)

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if _is_admin(request.user) or (hasattr(request.user, "employee_profile") and obj.employee_id == request.user.employee_profile.id):
            return Response(OvertimeRequestSerializer(obj).data, status=status.HTTP_200_OK)
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)


class EmployeeDocumentsAPI(DebugForce200Mixin, APIView):
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == 'GET' and settings.DEBUG:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        employee_param = request.query_params.get("employee")
        employee = _resolve_employee(employee_param)

        if _is_admin(request.user):
            qs = EmployeeDocument.objects.select_related("employee", "employee__user").all()
            if employee:
                qs = qs.filter(employee=employee)
        else:
            if not getattr(request.user, "is_authenticated", False):
                qs = EmployeeDocument.objects.select_related("employee", "employee__user").all()
                if employee:
                    qs = qs.filter(employee=employee)
                return Response(
                    EmployeeDocumentSerializer(qs, many=True, context={"request": request}).data,
                    status=status.HTTP_200_OK,
                )
            elif not hasattr(request.user, "employee_profile"):
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            if employee and employee.id != request.user.employee_profile.id:
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            qs = EmployeeDocument.objects.select_related("employee", "employee__user").filter(employee=request.user.employee_profile)

        return Response(
            EmployeeDocumentSerializer(qs, many=True, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        if not hasattr(request.user, "employee_profile"):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        payload = request.data.copy()
        payload["employee"] = request.user.employee_profile.id
        serializer = EmployeeDocumentSerializer(data=payload, context={"request": request})
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(
            EmployeeDocumentSerializer(obj, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class EmployeeDocumentDetailAPI(DebugForce200Mixin, APIView):
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == 'GET' and settings.DEBUG:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_object(self, pk):
        try:
            return EmployeeDocument.objects.select_related("employee", "employee__user").get(pk=pk)
        except EmployeeDocument.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not getattr(request.user, "is_authenticated", False) and settings.DEBUG:
            return Response(EmployeeDocumentSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)
        if _is_admin(request.user) or (hasattr(request.user, "employee_profile") and obj.employee_id == request.user.employee_profile.id):
            return Response(EmployeeDocumentSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    def patch(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if _is_admin(request.user):
            data = {}
            if "status" in request.data:
                data["status"] = _normalize_document_status(request.data.get("status"))
            serializer = EmployeeDocumentSerializer(obj, data=data, partial=True, context={"request": request})
            serializer.is_valid(raise_exception=True)
            obj = serializer.save()
            return Response(EmployeeDocumentSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)

        if not hasattr(request.user, "employee_profile") or obj.employee_id != request.user.employee_profile.id:
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        data = {}
        for field in ("title", "description", "document_type", "file"):
            if field in request.data:
                value = request.data.get(field)
                if field == "file" and value in (None, "", "null"):
                    continue
                if field == "file" and not isinstance(value, UploadedFile):
                    continue
                data[field] = value

        serializer = EmployeeDocumentSerializer(obj, data=data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(EmployeeDocumentSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _is_admin(request.user) and not (hasattr(request.user, "employee_profile") and obj.employee_id == request.user.employee_profile.id):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployeeTicketsAPI(DebugForce200Mixin, APIView):
    disable_force_200 = True
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == 'GET' and settings.DEBUG:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        employee_param = request.query_params.get("employee")
        assigned_to_param = request.query_params.get("assigned_to")
        unassigned = str(request.query_params.get("unassigned", "")).strip().lower() in {"1", "true", "yes"}
        status_param = request.query_params.get("status")
        priority_param = request.query_params.get("priority")
        search = str(request.query_params.get("search", "")).strip()
        ordering = str(request.query_params.get("ordering", "-created_at")).strip() or "-created_at"

        employee = _resolve_employee(employee_param)

        qs = EmployeeTicket.objects.select_related(
            "employee",
            "employee__user",
            "created_by",
            "assigned_to",
            "assigned_to__user",
            "assigned_by",
        ).all()

        is_admin = _is_admin(request.user)

        if not is_admin and not (getattr(request.user, "is_authenticated", False) or settings.DEBUG):
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)

        if is_admin:
            if employee:
                qs = qs.filter(employee=employee)
        else:
            if not hasattr(request.user, "employee_profile"):
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            me = request.user.employee_profile
            if assigned_to_param and str(assigned_to_param).strip().lower() == "me":
                qs = qs.filter(assigned_to=me)
            else:
                if employee and employee.id != me.id:
                    return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
                # Employee views should include owned + reassigned tickets.
                qs = qs.filter(Q(employee=me) | Q(assigned_to=me))

        if assigned_to_param and str(assigned_to_param).strip().lower() != "me":
            try:
                qs = qs.filter(assigned_to_id=int(str(assigned_to_param).strip()))
            except Exception:
                pass

        if unassigned:
            qs = qs.filter(assigned_to__isnull=True)

        if status_param:
            raw = [s.strip() for s in str(status_param).split(",") if s.strip()]
            mapped = []
            for s in raw:
                low = s.lower()
                if low in {"pending", "open"}:
                    mapped.append("open")
                elif low in {"in-progress", "in_progress"}:
                    mapped.append("in_progress")
                elif low in {"resolved"}:
                    mapped.append("resolved")
                elif low in {"closed"}:
                    mapped.append("closed")
            if mapped:
                qs = qs.filter(status__in=mapped)

        if priority_param:
            raw = [s.strip() for s in str(priority_param).split(",") if s.strip()]
            if raw:
                qs = qs.filter(priority__in=raw)

        if search:
            qs = qs.filter(Q(ticket_number__icontains=search) | Q(title__icontains=search))

        allowed_ordering = {
            "created_at",
            "-created_at",
            "updated_at",
            "-updated_at",
            "priority",
            "-priority",
            "status",
            "-status",
        }
        if ordering in allowed_ordering:
            qs = qs.order_by(ordering)
        else:
            qs = qs.order_by("-created_at")

        paginator = DefaultPageNumberPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        data = EmployeeTicketListSerializer(page, many=True, context={"request": request}).data
        return paginator.get_paginated_response(data)

    def post(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        payload = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if "assigned_to_id" not in payload:
            if "assigned_to" in payload:
                assigned = payload.get("assigned_to")
                if isinstance(assigned, dict):
                    payload["assigned_to_id"] = assigned.get("id")
                else:
                    payload["assigned_to_id"] = assigned
            elif "new_employee_id" in payload:
                payload["assigned_to_id"] = payload.get("new_employee_id")

        serializer = EmployeeTicketDetailSerializer(data=payload, context={"request": request})
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            obj = serializer.save(created_by=request.user)
        return Response(EmployeeTicketDetailSerializer(obj, context={"request": request}).data, status=status.HTTP_201_CREATED)


class EmployeeTicketDetailAPI(DebugForce200Mixin, APIView):
    disable_force_200 = True
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_permissions(self):
        if self.request.method == 'GET' and settings.DEBUG:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get_object(self, pk):
        try:
            return EmployeeTicket.objects.select_related(
                "employee",
                "employee__user",
                "created_by",
                "assigned_to",
                "assigned_to__user",
                "assigned_by",
            ).prefetch_related("attachments", "assignment_history", "comments").get(pk=pk)
        except EmployeeTicket.DoesNotExist:
            return None

    def get(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if _is_admin(request.user):
            return Response(EmployeeTicketDetailSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)
        if not getattr(request.user, "is_authenticated", False) and settings.DEBUG:
            return Response(EmployeeTicketDetailSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)
        if hasattr(request.user, "employee_profile"):
            me = request.user.employee_profile
            if obj.employee_id == me.id or getattr(obj, "assigned_to_id", None) == me.id:
                return Response(EmployeeTicketDetailSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)
        return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

    def patch(self, request, pk):
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _is_admin(request.user):
            if not _can_access_ticket(request.user, obj):
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            comment_keys = [
                "text",
                "comment",
                "message",
                "employee_comment",
                "commenttext",
                "commentText",
                "comment_text",
                "work",
                "work_update",
                "workUpdate",
                "update",
            ]
            text = None
            for k in comment_keys:
                if k in request.data:
                    text = request.data.get(k)
                    break

            status_value = request.data.get("status", None)
            if status_value not in (None, "", "null"):
                mapped_status = _ticket_status_from_api(status_value)
                if mapped_status in {"open", "in_progress", "resolved", "closed"}:
                    obj.status = mapped_status
                    obj.save(update_fields=["status", "updated_at"])

            if isinstance(text, str) and text.strip():
                EmployeeTicketComment.objects.create(
                    ticket=obj,
                    author=request.user,
                    author_employee=getattr(request.user, "employee_profile", None) if getattr(request.user, "is_authenticated", False) else None,
                    text=text.strip(),
                )

            if (status_value in (None, "", "null")) and not (isinstance(text, str) and text.strip()):
                return Response(
                    {
                        "detail": "No writable fields for employee",
                        "allowed": ["status"] + comment_keys,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            obj = self.get_object(pk)
            return Response(EmployeeTicketDetailSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)
        payload = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if "assigned_to_id" not in payload:
            if "assigned_to" in payload:
                assigned = payload.get("assigned_to")
                if isinstance(assigned, dict):
                    payload["assigned_to_id"] = assigned.get("id")
                else:
                    payload["assigned_to_id"] = assigned
            elif "new_employee_id" in payload:
                payload["assigned_to_id"] = payload.get("new_employee_id")

        serializer = EmployeeTicketDetailSerializer(obj, data=payload, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            obj = serializer.save()

        return Response(EmployeeTicketDetailSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)

    def post(self, request, pk):
        return self.patch(request, pk)

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        if not _is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        obj = self.get_object(pk)
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployeeTicketsStatsAPI(DebugForce200Mixin, APIView):
    disable_force_200 = True
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]

    def get_permissions(self):
        if self.request.method == 'GET' and settings.DEBUG:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        qs = EmployeeTicket.objects.all()
        is_admin = _is_admin(request.user)

        if not is_admin:
            if not hasattr(request.user, "employee_profile"):
                if settings.DEBUG:
                    return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_200_OK)
                return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)
            me = request.user.employee_profile
            qs = qs.filter(Q(employee=me) | Q(assigned_to=me))

        by_status = {
            "pending": qs.filter(status="open").count(),
            "in_progress": qs.filter(status="in_progress").count(),
            "resolved": qs.filter(status="resolved").count(),
            "closed": qs.filter(status="closed").count(),
        }

        by_priority = {}
        for p, _ in EmployeeTicket.PRIORITY_CHOICES:
            by_priority[p] = qs.filter(priority=p).count()

        return Response(
            {
                "total": qs.count(),
                "unassigned": qs.filter(assigned_to__isnull=True).count(),
                "by_status": by_status,
                "by_priority": by_priority,
            },
            status=status.HTTP_200_OK,
        )


class EmployeeTicketReassignAPI(DebugForce200Mixin, APIView):
    disable_force_200 = True
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not _is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        obj = EmployeeTicket.objects.select_related("assigned_to").filter(pk=pk).first()
        if not obj:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        new_employee_id = request.data.get("new_employee_id", request.data.get("assigned_to_id"))
        reason = str(request.data.get("reason", "") or "").strip()
        if new_employee_id in (None, "", "null"):
            return Response({"detail": "new_employee_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_assignee = EmployeeProfile.objects.get(pk=int(str(new_employee_id).strip()))
        except Exception:
            return Response({"detail": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            from_employee = obj.assigned_to
            obj.assigned_to = new_assignee
            obj.assigned_by = request.user
            obj.assigned_at = timezone.now()
            obj.save(update_fields=["assigned_to", "assigned_by", "assigned_at", "updated_at"])
            EmployeeTicketAssignmentHistory.objects.create(
                ticket=obj,
                from_employee=from_employee,
                to_employee=new_assignee,
                by=request.user,
                reason=reason,
            )

        obj = EmployeeTicket.objects.select_related(
            "employee",
            "employee__user",
            "created_by",
            "assigned_to",
            "assigned_to__user",
            "assigned_by",
        ).prefetch_related("attachments", "assignment_history").get(pk=obj.pk)
        return Response(EmployeeTicketDetailSerializer(obj, context={"request": request}).data, status=status.HTTP_200_OK)


class EmployeeTicketBulkAssignAPI(DebugForce200Mixin, APIView):
    disable_force_200 = True
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    parser_classes = [JSONParser, FormParser, MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        ticket_ids = request.data.get("ticket_ids", [])
        new_employee_id = request.data.get("new_employee_id", request.data.get("assigned_to_id"))
        reason = str(request.data.get("reason", "") or "").strip()

        if not isinstance(ticket_ids, list) or not ticket_ids:
            return Response({"detail": "ticket_ids must be a non-empty list"}, status=status.HTTP_400_BAD_REQUEST)
        if new_employee_id in (None, "", "null"):
            return Response({"detail": "new_employee_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_assignee = EmployeeProfile.objects.get(pk=int(str(new_employee_id).strip()))
        except Exception:
            return Response({"detail": "Employee not found"}, status=status.HTTP_404_NOT_FOUND)

        cleaned_ids = []
        for tid in ticket_ids:
            try:
                cleaned_ids.append(int(str(tid).strip()))
            except Exception:
                continue
        if not cleaned_ids:
            return Response({"detail": "No valid ticket ids"}, status=status.HTTP_400_BAD_REQUEST)

        updated = 0
        with transaction.atomic():
            qs = EmployeeTicket.objects.select_for_update().select_related("assigned_to").filter(pk__in=cleaned_ids)
            for t in qs:
                from_employee = t.assigned_to
                if from_employee and from_employee.id == new_assignee.id:
                    continue
                t.assigned_to = new_assignee
                t.assigned_by = request.user
                t.assigned_at = timezone.now()
                t.save(update_fields=["assigned_to", "assigned_by", "assigned_at", "updated_at"])
                EmployeeTicketAssignmentHistory.objects.create(
                    ticket=t,
                    from_employee=from_employee,
                    to_employee=new_assignee,
                    by=request.user,
                    reason=reason,
                )
                updated += 1

        return Response({"updated": updated}, status=status.HTTP_200_OK)


class EmployeeTicketCommentsAPI(DebugForce200Mixin, APIView):
    disable_force_200 = True
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_permissions(self):
        if self.request.method == 'GET' and settings.DEBUG:
            return [AllowAny()]
        return [IsAuthenticated()]

    def _get_ticket(self, pk):
        try:
            return EmployeeTicket.objects.select_related("employee", "assigned_to").get(pk=pk)
        except EmployeeTicket.DoesNotExist:
            return None

    def get(self, request, pk):
        ticket = self._get_ticket(pk)
        if not ticket:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not getattr(request.user, "is_authenticated", False) and settings.DEBUG:
            qs = EmployeeTicketComment.objects.filter(ticket=ticket).select_related("author", "author_employee", "author_employee__user").order_by("-created_at")
            return Response(EmployeeTicketCommentSerializer(qs, many=True, context={"request": request}).data, status=status.HTTP_200_OK)
        if not _can_access_ticket(request.user, ticket):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        qs = EmployeeTicketComment.objects.filter(ticket=ticket).select_related("author", "author_employee", "author_employee__user").order_by("-created_at")
        return Response(EmployeeTicketCommentSerializer(qs, many=True, context={"request": request}).data, status=status.HTTP_200_OK)

    def post(self, request, pk):
        ticket = self._get_ticket(pk)
        if not ticket:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        if not _can_access_ticket(request.user, ticket):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        text = request.data.get("text", None)
        if text is None:
            text = request.data.get("comment", None)
        if text is None:
            text = request.data.get("message", None)
        if not isinstance(text, str) or not text.strip():
            return Response({"detail": "text is required"}, status=status.HTTP_400_BAD_REQUEST)

        comment = EmployeeTicketComment.objects.create(
            ticket=ticket,
            author=request.user,
            author_employee=getattr(request.user, "employee_profile", None) if getattr(request.user, "is_authenticated", False) else None,
            text=text.strip(),
        )
        return Response(EmployeeTicketCommentSerializer(comment, context={"request": request}).data, status=status.HTTP_201_CREATED)


class EmployeeTicketCommentsFlatAPI(DebugForce200Mixin, APIView):
    disable_force_200 = True
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def get_permissions(self):
        if self.request.method == 'GET' and settings.DEBUG:
            return [AllowAny()]
        return [IsAuthenticated()]

    def get(self, request):
        ticket_param = request.query_params.get("ticket")
        if ticket_param in (None, "", "null", "undefined"):
            return Response([], status=status.HTTP_200_OK)
        try:
            ticket = EmployeeTicket.objects.select_related("employee", "assigned_to").get(pk=int(str(ticket_param).strip()))
        except Exception:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if not getattr(request.user, "is_authenticated", False) and settings.DEBUG:
            qs = EmployeeTicketComment.objects.filter(ticket=ticket).select_related("author", "author_employee", "author_employee__user").order_by("-created_at")
            return Response(EmployeeTicketCommentSerializer(qs, many=True, context={"request": request}).data, status=status.HTTP_200_OK)
        if not _can_access_ticket(request.user, ticket):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
        qs = EmployeeTicketComment.objects.filter(ticket=ticket).select_related("author", "author_employee", "author_employee__user").order_by("-created_at")
        return Response(EmployeeTicketCommentSerializer(qs, many=True, context={"request": request}).data, status=status.HTTP_200_OK)

    def post(self, request):
        ticket_value = request.data.get("ticket")
        if ticket_value in (None, "", "null", "undefined"):
            return Response({"detail": "ticket is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            ticket = EmployeeTicket.objects.select_related("employee", "assigned_to").get(pk=int(str(ticket_value).strip()))
        except Exception:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        if not _can_access_ticket(request.user, ticket):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        text = request.data.get("text", None)
        if text is None:
            text = request.data.get("comment", None)
        if text is None:
            text = request.data.get("message", None)
        if not isinstance(text, str) or not text.strip():
            return Response({"detail": "text is required"}, status=status.HTTP_400_BAD_REQUEST)

        comment = EmployeeTicketComment.objects.create(
            ticket=ticket,
            author=request.user,
            author_employee=getattr(request.user, "employee_profile", None) if getattr(request.user, "is_authenticated", False) else None,
            text=text.strip(),
        )
        return Response(EmployeeTicketCommentSerializer(comment, context={"request": request}).data, status=status.HTTP_201_CREATED)


class EmployeeMeAPI(DebugForce200Mixin, APIView):
    permission_classes = [AllowAny]
    authentication_classes = [QuietJWTAuthentication, SessionAuthentication]
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer]

    def get(self, request):
        if not getattr(request.user, "is_authenticated", False):
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_200_OK)
        if hasattr(request.user, "employee_profile"):
            return Response(
                EmployeeProfileSerializer(request.user.employee_profile, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )
        project = Project.objects.filter(project_manager=request.user).order_by("-updated_at").first()
        return Response(
            {
                "user_email": getattr(request.user, "email", None),
                "user_name": f"{getattr(request.user, 'firstname', '')} {getattr(request.user, 'lastname', '')}".strip()
                or getattr(request.user, "username", None),
                "private_project": getattr(project, "id", None) if project else None,
                "private_project_title": getattr(project, "title", None) if project else None,
            },
            status=status.HTTP_200_OK,
        )


class EmployeeSetPasswordAPI(DebugForce200Mixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not _is_admin(request.user):
            return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)

        try:
            employee = EmployeeProfile.objects.select_related("user").get(pk=pk)
        except EmployeeProfile.DoesNotExist:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        password = request.data.get("password")
        if not isinstance(password, str) or not password:
            return Response({"detail": "password is required"}, status=status.HTTP_400_BAD_REQUEST)

        employee.user.set_password(password)
        employee.user.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class LeaveBalanceAPI(DebugForce200Mixin, APIView):
    permission_classes = [IsAuthenticated]

    MONTHLY_LEAVE_TOTAL = 24

    def get(self, request):
        employee_param = request.query_params.get("employee")

        if _is_admin(request.user):
            employee = _resolve_employee(employee_param) if employee_param else None
            if not employee:
                return Response({"detail": "employee is required"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            if not hasattr(request.user, "employee_profile"):
                return Response({"detail": "Forbidden"}, status=status.HTTP_403_FORBIDDEN)
            employee = request.user.employee_profile

        today = date.today()
        month_start = today.replace(day=1)
        if today.month == 12:
            next_month_start = date(today.year + 1, 1, 1)
        else:
            next_month_start = date(today.year, today.month + 1, 1)
        month_end = next_month_start - timedelta(days=1)

        approved = LeaveRequest.objects.filter(
            employee=employee,
            status="approved",
            end_date__gte=month_start,
            start_date__lte=month_end,
        )

        used_days = 0
        for lr in approved:
            start = max(lr.start_date, month_start)
            end = min(lr.end_date, month_end)
            delta = (end - start).days + 1
            if delta > 0:
                used_days += delta

        total = self.MONTHLY_LEAVE_TOTAL
        remaining = max(total - used_days, 0)

        return Response(
            {
                "employee": employee.id,
                "year": today.year,
                "month": today.month,
                "period_start": month_start,
                "period_end": month_end,
                "total": total,
                "used": used_days,
                "remaining": remaining,
            },
            status=status.HTTP_200_OK,
        )


