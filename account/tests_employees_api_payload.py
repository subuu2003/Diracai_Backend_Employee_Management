import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from account.employee_models import EmployeeProfile
from account.employee_serializers import EmployeeAdminSerializer


User = get_user_model()


class EmployeesApiPayloadTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin_emp_payload",
            email="admin_emp_payload@example.com",
            phoneno="9000000041",
            password="pass1234",
        )
        self.admin.is_staff = True
        self.admin.save()

    def test_create_employee_accepts_login_id_as_phone(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/employees/",
            data=json.dumps({"login_id": "9000000099", "name": "Test Emp", "designation": "Dev", "status": "active"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(EmployeeProfile.objects.filter(phone="9000000099").exists())

    def test_create_employee_accepts_login_id_as_email(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/employees/",
            data=json.dumps({"login_id": "emp900@example.com", "phone": "9000000088", "name": "Test Emp2"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(EmployeeProfile.objects.filter(user__email__iexact="emp900@example.com").exists())


class EmployeeAdminSerializerIntegrityErrorTests(TestCase):
    @patch("account.employee_serializers.User.objects.create_user")
    def test_create_surfaces_non_duplicate_integrity_error_details(self, create_user):
        create_user.side_effect = IntegrityError(
            'null value in column "hourlyrate" of relation "account_account" violates not-null constraint'
        )
        serializer = EmployeeAdminSerializer(
            data={"phone": "9000000199", "designation": "Dev", "status": "active"},
            context={"name": "Broken Schema", "password": "pass12345"},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        with self.assertRaises(ValidationError) as exc:
            serializer.save()

        self.assertIn("hourlyrate", str(exc.exception.detail.get("detail", "")))

    @patch("account.employee_serializers.User.objects.create_user")
    def test_create_keeps_duplicate_login_message_for_unique_constraint(self, create_user):
        create_user.side_effect = IntegrityError(
            'duplicate key value violates unique constraint "account_account_username_key"'
        )
        serializer = EmployeeAdminSerializer(
            data={"phone": "9000000200", "designation": "Dev", "status": "active"},
            context={"name": "Duplicate Login", "password": "pass12345"},
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

        with self.assertRaises(ValidationError) as exc:
            serializer.save()

        self.assertEqual(str(exc.exception.detail.get("email", "")), "Email/login already exists.")
