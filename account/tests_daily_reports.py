from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from account.employee_models import EmployeeProfile, EmployeeTicket, DailyReport

User = get_user_model()


class DailyReportTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create employee user 1
        self.user1 = User.objects.create_user(
            username="emp1@test.com",
            email="emp1@test.com",
            phoneno="9000000001",
            password="Password123!",
        )
        self.user1.firstname = "Alice"
        self.user1.lastname = "Employee"
        self.user1.save()
        self.emp1 = EmployeeProfile.objects.create(
            user=self.user1,
            employee_id="DIR-TEST-001",
            phone="9000000001",
            status="active",
        )

        # Create employee user 2
        self.user2 = User.objects.create_user(
            username="emp2@test.com",
            email="emp2@test.com",
            phoneno="9000000002",
            password="Password123!",
        )
        self.user2.firstname = "Bob"
        self.user2.lastname = "Employee"
        self.user2.save()
        self.emp2 = EmployeeProfile.objects.create(
            user=self.user2,
            employee_id="DIR-TEST-002",
            phone="9000000002",
            status="active",
        )

        # Create admin user
        self.admin_user = User.objects.create_superuser(
            username="admin@test.com",
            email="admin@test.com",
            phoneno="9000000000",
            password="AdminPassword123!",
        )

        # Create an existing ticket
        self.ticket1 = EmployeeTicket.objects.create(
            employee=self.emp1,
            ticket_number="TCK-2026-000001",
            title="Fix login bug",
            description="Detail description",
            status="open",
            priority="high",
            created_by=self.user1,
        )
        self.ticket2 = EmployeeTicket.objects.create(
            employee=self.emp1,
            ticket_number="TCK-2026-000002",
            title="Database indexing",
            description="Optimize queries",
            status="in_progress",
            priority="medium",
            created_by=self.user1,
        )

    def test_employee_create_daily_report_with_valid_tickets(self):
        self.client.force_authenticate(user=self.user1)
        initial_ticket_count = EmployeeTicket.objects.count()

        payload = {
            "date": "2026-10-10",
            "work_completed": "Resolved login validation and pushed changes.",
            "work_in_progress": "Reviewing database indexing.",
            "pending_work": "Waiting on code review.",
            "ticket_ids": f"{self.ticket1.ticket_number}, {self.ticket2.id}",
        }

        response = self.client.post("/api/daily-reports/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = response.json()
        self.assertEqual(data["date"], "2026-10-10")
        self.assertEqual(data["work_completed"], payload["work_completed"])
        self.assertEqual(len(data["tickets"]), 2)
        ticket_nums = [t["ticket_number"] for t in data["tickets"]]
        self.assertIn("TCK-2026-000001", ticket_nums)
        self.assertIn("TCK-2026-000002", ticket_nums)

        # Ensure NO new tickets were created
        self.assertEqual(EmployeeTicket.objects.count(), initial_ticket_count)

    def test_employee_create_daily_report_with_invalid_tickets_rejected(self):
        self.client.force_authenticate(user=self.user1)
        initial_ticket_count = EmployeeTicket.objects.count()
        initial_report_count = DailyReport.objects.count()

        payload = {
            "date": "2026-10-10",
            "work_completed": "Worked on some tasks.",
            "ticket_ids": f"{self.ticket1.ticket_number}, NONEXISTENT-999, 88888",
        }

        response = self.client.post("/api/daily-reports/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn("invalid_tickets", data)
        self.assertIn("NONEXISTENT-999", data["invalid_tickets"])
        self.assertIn("88888", data["invalid_tickets"])

        # Ensure NO report and NO tickets created
        self.assertEqual(DailyReport.objects.count(), initial_report_count)
        self.assertEqual(EmployeeTicket.objects.count(), initial_ticket_count)

    def test_employee_isolation(self):
        # Create a report for Alice
        report = DailyReport.objects.create(
            employee=self.emp1,
            date=date(2026, 10, 10),
            work_completed="Alice's private work report.",
        )

        # Authenticate as Bob and try to access Alice's report
        self.client.force_authenticate(user=self.user2)
        response = self.client.get(f"/api/daily-reports/{report.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Bob cannot patch Alice's report
        patch_res = self.client.patch(
            f"/api/daily-reports/{report.id}/",
            {"work_completed": "Hacked content"},
            format="json"
        )
        self.assertEqual(patch_res.status_code, status.HTTP_403_FORBIDDEN)

        # Bob's report list only shows Bob's reports
        list_res = self.client.get("/api/daily-reports/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_res.json()), 0)

    def test_admin_can_view_and_filter_daily_reports_by_employee_and_month(self):
        # Create reports across different months for Alice
        r1 = DailyReport.objects.create(
            employee=self.emp1,
            date=date(2026, 10, 1),
            work_completed="October report 1",
        )
        r2 = DailyReport.objects.create(
            employee=self.emp1,
            date=date(2026, 9, 15),
            work_completed="September report",
        )

        # Admin logs in
        self.client.force_authenticate(user=self.admin_user)

        # Fetch for Alice with month filter for October
        res = self.client.get(f"/api/daily-reports/?employee={self.emp1.id}&month=2026-10")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], r1.id)

        # Also verify the employee-daily-reports alias endpoint used by admin panel
        res_emp_alias = self.client.get(f"/api/employee-daily-reports/?employee={self.emp1.id}&month=2026-10")
        self.assertEqual(res_emp_alias.status_code, status.HTTP_200_OK)
        data_emp_alias = res_emp_alias.json()
        self.assertEqual(len(data_emp_alias), 1)
        self.assertEqual(data_emp_alias[0]["id"], r1.id)

        # Fetch for Alice with month filter for September
        res_sep = self.client.get(f"/api/daily-reports/?employee={self.emp1.id}&month=2026-09")
        self.assertEqual(res_sep.status_code, status.HTTP_200_OK)
        data_sep = res_sep.json()
        self.assertEqual(len(data_sep), 1)
        self.assertEqual(data_sep[0]["id"], r2.id)

    def test_daily_report_patch_and_delete(self):
        self.client.force_authenticate(user=self.user1)
        report = DailyReport.objects.create(
            employee=self.emp1,
            date=date(2026, 10, 10),
            work_completed="Initial work",
        )

        # Patch work update and tickets
        patch_res = self.client.patch(
            f"/api/daily-reports/{report.id}/",
            {
                "work_completed": "Updated work description",
                "ticket_ids": self.ticket1.ticket_number,
            },
            format="json",
        )
        self.assertEqual(patch_res.status_code, status.HTTP_200_OK)
        data = patch_res.json()
        self.assertEqual(data["work_completed"], "Updated work description")
        self.assertEqual(len(data["tickets"]), 1)
        self.assertEqual(data["tickets"][0]["ticket_number"], self.ticket1.ticket_number)

        # Delete
        del_res = self.client.delete(f"/api/daily-reports/{report.id}/")
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(DailyReport.objects.filter(id=report.id).exists())
