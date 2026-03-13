import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from account.employee_models import EmployeeProfile


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
