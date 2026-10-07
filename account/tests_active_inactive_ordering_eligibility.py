import json
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from account.employee_models import (
    EmployeeProfile,
    EmployeeTicket,
    PrivateProjectPlan,
    PrivateProjectAssignment,
)
from account.models import Project, ProjectMembership

User = get_user_model()


class ActiveInactiveOrderingAndEligibilityTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin = User.objects.create_user(
            username="admin_test",
            email="admin_test@example.com",
            phoneno="9000000010",
            password="pass1234",
        )
        self.admin.is_staff = True
        self.admin.save()

        # Create active employee
        self.active_user = User.objects.create_user(
            username="active_emp",
            email="active_emp@example.com",
            phoneno="9000000011",
            password="pass1234",
        )
        self.active_employee = EmployeeProfile.objects.create(
            user=self.active_user,
            employee_id="DI90001",
            phone="9000000011",
            designation="Active Dev",
            status="active",
        )

        # Create inactive employee
        self.inactive_user = User.objects.create_user(
            username="inactive_emp",
            email="inactive_emp@example.com",
            phoneno="9000000012",
            password="pass1234",
        )
        self.inactive_employee = EmployeeProfile.objects.create(
            user=self.inactive_user,
            employee_id="DI90002",
            phone="9000000012",
            designation="Inactive Dev",
            status="inactive",
        )

        # Create project and private plan
        self.project = Project.objects.create(
            title="Private Test Project",
            description="Test Description",
            status="in_progress",
        )
        self.plan = PrivateProjectPlan.objects.create(
            project=self.project,
            project_name="Private Plan",
        )

    def test_employee_api_ordering_active_before_inactive(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.get("/api/employees/?nopaginate=true")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreaterEqual(len(data), 2)

        # Verify active appears before inactive
        active_indices = [i for i, e in enumerate(data) if e.get("status", "").lower() == "active"]
        inactive_indices = [i for i, e in enumerate(data) if e.get("status", "").lower() == "inactive"]
        self.assertTrue(len(active_indices) > 0)
        self.assertTrue(len(inactive_indices) > 0)
        self.assertLess(max(active_indices), min(inactive_indices))

        # Change active employee to inactive, and inactive to active
        self.active_employee.status = "inactive"
        self.active_employee.save()
        self.inactive_employee.status = "active"
        self.inactive_employee.save()

        res2 = self.client.get("/api/employees/?nopaginate=true")
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        new_active_indices = [i for i, e in enumerate(data2) if e.get("status", "").lower() == "active"]
        new_inactive_indices = [i for i, e in enumerate(data2) if e.get("status", "").lower() == "inactive"]
        self.assertLess(max(new_active_indices), min(new_inactive_indices))
        # Now DI90002 is active and DI90001 is inactive
        self.assertEqual(data2[new_active_indices[0]]["employee_id"], "DI90002")

    def test_create_ticket_with_inactive_employee_fails(self):
        self.client.force_authenticate(user=self.admin)
        payload = {
            "employee": self.inactive_employee.id,
            "title": "Inactive Employee Ticket",
            "description": "Details",
            "priority": "high",
        }
        res = self.client.post("/api/employee-tickets/", data=payload, format="json")
        self.assertEqual(res.status_code, 400)

    def test_create_ticket_with_active_employee_succeeds(self):
        self.client.force_authenticate(user=self.admin)
        payload = {
            "employee": self.active_employee.id,
            "title": "Active Employee Ticket",
            "description": "Details",
            "priority": "high",
        }
        res = self.client.post("/api/employee-tickets/", data=payload, format="json")
        self.assertEqual(res.status_code, 201)

    def test_reassign_ticket_to_inactive_employee_fails(self):
        ticket = EmployeeTicket.objects.create(
            employee=self.active_employee,
            assigned_to=self.active_employee,
            title="Ticket to Reassign",
            created_by=self.admin,
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f"/api/employee-tickets/{ticket.id}/reassign/",
            data={"new_employee_id": self.inactive_employee.id},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_bulk_assign_tickets_to_inactive_employee_fails(self):
        ticket = EmployeeTicket.objects.create(
            employee=self.active_employee,
            assigned_to=self.active_employee,
            title="Ticket for Bulk Assign",
            created_by=self.admin,
        )
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/employee-tickets/bulk-assign/",
            data={"ticket_ids": [ticket.id], "new_employee_id": self.inactive_employee.id},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_assign_inactive_employee_to_private_project_fails(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f"/api/private-projects/{self.project.id}/plan/assignments/",
            data={"employee": self.inactive_employee.id, "designation": "Dev"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_assign_active_employee_to_private_project_succeeds(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f"/api/private-projects/{self.project.id}/plan/assignments/",
            data={"employee": self.active_employee.id, "designation": "Dev"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)

    def test_assign_inactive_employee_to_project_membership_fails(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            "/api/project-memberships/",
            data={
                "project": self.project.id,
                "employee": self.inactive_employee.id,
                "role": "member",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_existing_inactive_employee_assignments_preserved(self):
        # If an employee was already assigned while active, and later became inactive
        assignment = PrivateProjectAssignment.objects.create(
            plan=self.plan,
            employee=self.inactive_employee,
            designation="Already Assigned Dev",
        )
        ticket = EmployeeTicket.objects.create(
            employee=self.inactive_employee,
            assigned_to=self.inactive_employee,
            title="Existing Ticket",
            created_by=self.admin,
        )
        self.client.force_authenticate(user=self.admin)

        # Ticket detail still works and returns the existing assignment
        res_ticket = self.client.get(f"/api/employee-tickets/{ticket.id}/")
        self.assertEqual(res_ticket.status_code, 200)
        self.assertEqual(res_ticket.json()["employee_info"]["employee_code"], self.inactive_employee.employee_id)

        # Private project plan still lists the existing assignment
        res_plan = self.client.get(f"/api/private-projects/{self.project.id}/")
        self.assertEqual(res_plan.status_code, 200)
        assignments = res_plan.json().get("plan", {}).get("assignments", [])
        self.assertTrue(any(a["employee"] == self.inactive_employee.id for a in assignments))
