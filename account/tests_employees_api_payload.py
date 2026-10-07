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

    def test_get_employees_paginated_and_metadata(self):
        self.client.force_authenticate(user=self.admin)
        for i in range(1, 4):
            u = User.objects.create_user(
                username=f"emp_page_{i}",
                email=f"emp_page_{i}@example.com",
                phoneno=f"910000000{i}",
                password="pass",
            )
            u.firstname = f"Emp{i}"
            u.lastname = "Test"
            u.save()
            EmployeeProfile.objects.create(
                user=u,
                employee_id=f"DI9900{i}",
                phone=f"910000000{i}",
                designation="Frontend Developer" if i == 1 else "Backend Developer",
                status="active" if i < 3 else "inactive",
            )

        # Page 1 with page_size=2
        res = self.client.get("/api/employees/?page=1&page_size=2")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("count", data)
        self.assertGreaterEqual(data["count"], 3)
        self.assertEqual(len(data["results"]), 2)
        self.assertEqual(data.get("current_page"), 1)
        self.assertEqual(data.get("page_size"), 2)
        self.assertTrue(data.get("total_pages") >= 2)
        self.assertIsNotNone(data.get("next"))

        # Page 2 with page_size=2
        res2 = self.client.get("/api/employees/?page=2&page_size=2")
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2.get("current_page"), 2)
        self.assertIsNotNone(data2.get("previous"))

    def test_get_employees_search_and_filters(self):
        self.client.force_authenticate(user=self.admin)
        u1 = User.objects.create_user(
            username="emp_search_alpha",
            email="alpha@example.com",
            phoneno="9200000001",
            password="pass",
        )
        u1.firstname = "Alpha"
        u1.lastname = "Dev"
        u1.save()
        EmployeeProfile.objects.create(
            user=u1,
            employee_id="DI_ALPHA",
            phone="9200000001",
            designation="Mobile App Developer",
            status="active",
        )

        u2 = User.objects.create_user(
            username="emp_search_beta",
            email="beta@example.com",
            phoneno="9200000002",
            password="pass",
        )
        u2.firstname = "Beta"
        u2.lastname = "Dev"
        u2.save()
        EmployeeProfile.objects.create(
            user=u2,
            employee_id="DI_BETA",
            phone="9200000002",
            designation="Blockchain Developer",
            status="inactive",
        )

        # Search by keyword
        res_search = self.client.get("/api/employees/?search=Alpha")
        self.assertEqual(res_search.status_code, 200)
        data_search = res_search.json()
        self.assertEqual(data_search["count"], 1)
        self.assertEqual(data_search["results"][0]["employee_id"], "DI_ALPHA")

        # Filter by designation
        res_desig = self.client.get("/api/employees/?designation=Blockchain Developer")
        self.assertEqual(res_desig.status_code, 200)
        data_desig = res_desig.json()
        self.assertTrue(any(e["employee_id"] == "DI_BETA" for e in data_desig["results"]))

        # Filter by status
        res_status = self.client.get("/api/employees/?status=inactive&search=Beta")
        self.assertEqual(res_status.status_code, 200)
        data_status = res_status.json()
        self.assertEqual(data_status["count"], 1)
        self.assertEqual(data_status["results"][0]["employee_id"], "DI_BETA")


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
