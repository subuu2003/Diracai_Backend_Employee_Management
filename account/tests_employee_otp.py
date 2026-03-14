from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from account.employee_models import EmployeeProfile


User = get_user_model()


class EmployeeOtpFallbackTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="otp_emp",
            email="otp_emp@example.com",
            phoneno="9000000061",
            password="pass1234",
        )
        self.employee = EmployeeProfile.objects.create(
            user=self.user,
            employee_id="DI60001",
            phone="9000000061",
            designation="Developer",
            status="active",
        )

    @patch("account.employee_views.send_otp_via_sms", return_value=False)
    @patch("account.employee_views.send_otp_via_email", return_value=False)
    def test_login_request_returns_fallback_otp_when_no_channel_is_configured(self, _email_mock, _sms_mock):
        response = self.client.post(
            "/api/employee/login/request/",
            data={"login_id": "otp_emp@example.com", "password": "pass1234"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["email_sent"], False)
        self.assertEqual(payload["sms_sent"], False)
        self.assertIn("otp_code", payload)
        self.assertEqual(len(str(payload["otp_code"])), 6)

    @patch("account.employee_views.send_otp_via_sms", return_value=False)
    @patch("account.employee_views.send_otp_via_email", return_value=False)
    def test_resend_returns_fallback_otp_when_no_channel_is_configured(self, _email_mock, _sms_mock):
        response = self.client.post(
            "/api/employee/otp/resend/",
            data={"employee_id": self.employee.employee_id},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["email_sent"], False)
        self.assertEqual(payload["sms_sent"], False)
        self.assertIn("otp_code", payload)
        self.assertEqual(len(str(payload["otp_code"])), 6)
