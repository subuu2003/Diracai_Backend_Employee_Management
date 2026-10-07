import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from account.employee_models import (
    EmployeeProfile,
    EmployeeTicket,
    CurrentProjectPlan,
    PrivateProjectPlan,
    PrivateProjectAssignment,
    CurrentProjectAssignment,
    PrivateProjectTicketAssignment,
    CurrentProjectTicketAssignment,
)
from account.models import Project


User = get_user_model()


class EmployeeTicketsAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin = User.objects.create_user(
            username="admin_ticket",
            email="admin_ticket@example.com",
            phoneno="9000000003",
            password="pass1234",
        )
        self.admin.is_staff = True
        self.admin.save()

        self.emp_user = User.objects.create_user(
            username="emp_ticket",
            email="emp_ticket@example.com",
            phoneno="9000000004",
            password="pass1234",
        )
        self.employee = EmployeeProfile.objects.create(
            user=self.emp_user,
            employee_id="DI30001",
            phone="9000000004",
            designation="Dev",
            status="active",
        )

    def test_admin_can_create_ticket_and_employee_can_list(self):
        self.client.force_authenticate(user=self.admin)
        payload = {
            "employee": self.employee.id,
            "title": "Fix bug",
            "description": "Details",
            "priority": "high",
        }
        res = self.client.post("/api/employee-tickets/", data=payload, format="json")
        self.assertEqual(res.status_code, 201)
        ticket_id = res.json().get("id")
        self.assertTrue(ticket_id)

        self.client.force_authenticate(user=self.emp_user)
        res2 = self.client.get("/api/employee-tickets/")
        self.assertEqual(res2.status_code, 200)
        payload2 = res2.json()
        items = payload2.get("results", []) if isinstance(payload2, dict) else payload2
        self.assertTrue(any(t.get("id") == ticket_id for t in items))
        created = next((t for t in items if t.get("id") == ticket_id), None)
        self.assertIsNotNone(created)
        self.assertTrue(bool(created.get("ticket_number")))
        self.assertEqual(created.get("status"), "pending")
        self.assertIn("employee", created)
        self.assertEqual(created.get("employee", {}).get("id"), self.employee.id)

    def test_ticket_assignments_persist_on_current_project_plan(self):
        self.client.force_authenticate(user=self.admin)

        project = Project.objects.create(title="P", description="D", status="planned")
        plan = CurrentProjectPlan.objects.create(project=project, project_name="P")

        ticket = EmployeeTicket.objects.create(
            employee=self.employee,
            title="Investigate",
            description="",
            created_by=self.admin,
        )

        patch_payload = {
            "timeline": "t1",
            "ticket_assignments": [
                {
                    "ticket": ticket.id,
                    "employee": self.employee.id,
                    "assign_date": "2026-03-10",
                    "expire_date": "2026-03-20",
                }
            ],
        }

        res = self.client.patch(
            f"/api/private-projects/{project.id}/plan/",
            data=json.dumps(patch_payload),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)

        plan.refresh_from_db()
        self.assertEqual(plan.timeline, "t1")
        self.assertEqual(plan.ticket_assignments.count(), 1)
        ta = plan.ticket_assignments.first()
        self.assertEqual(ta.ticket_id, ticket.id)
        self.assertEqual(ta.employee_id, self.employee.id)

    def test_employee_can_post_and_fetch_ticket_comments(self):
        ticket = EmployeeTicket.objects.create(
            employee=self.employee,
            title="Comment me",
            description="",
            created_by=self.admin,
        )

        self.client.force_authenticate(user=self.emp_user)
        res = self.client.post(
            f"/api/employee-tickets/{ticket.id}/comments/",
            data={"text": "work update 1"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)

        res2 = self.client.get(f"/api/employee-tickets/{ticket.id}/comments/")
        self.assertEqual(res2.status_code, 200)
        items = res2.json()
        self.assertTrue(any(c.get("text") == "work update 1" for c in items))

        res3 = self.client.get(f"/api/employee-ticket-comments/?ticket={ticket.id}")
        self.assertEqual(res3.status_code, 200)
        items3 = res3.json()
        self.assertTrue(any(c.get("text") == "work update 1" for c in items3))

        res4 = self.client.patch(
            f"/api/employee-tickets/{ticket.id}/",
            data={"employee_comment": "work update 2"},
            format="json",
        )
        self.assertEqual(res4.status_code, 200)
        res5 = self.client.get(f"/api/employee-tickets/{ticket.id}/comments/")
        self.assertEqual(res5.status_code, 200)
        items5 = res5.json()
        self.assertTrue(any(c.get("text") == "work update 2" for c in items5))

        res6 = self.client.patch(
            f"/api/employee-tickets/{ticket.id}/",
            data={"commenttext": "work update 3"},
            format="json",
        )
        self.assertEqual(res6.status_code, 200)

        res7 = self.client.patch(
            f"/api/employee-tickets/{ticket.id}/",
            data={"status": "in_progress"},
            format="json",
        )
        self.assertEqual(res7.status_code, 200)
        self.assertEqual(res7.json().get("status"), "in_progress")

    def test_employee_can_post_comment_with_attachment(self):
        ticket = EmployeeTicket.objects.create(
            employee=self.employee,
            title="Attach file",
            description="",
            created_by=self.admin,
        )

        self.client.force_authenticate(user=self.emp_user)
        file_content = b"hello ticket attachment"
        uploaded = self.client.post(
            f"/api/employee-tickets/{ticket.id}/comments/",
            data={
                "text": "with attachment",
                "files": [SimpleUploadedFile("note.txt", file_content, content_type="text/plain")],
            },
            format="multipart",
        )
        self.assertEqual(uploaded.status_code, 201)
        body = uploaded.json()
        self.assertEqual(body.get("text"), "with attachment")
        self.assertTrue(body.get("attachments"))
        comment = ticket.comments.get(text="with attachment")
        self.assertTrue(ticket.attachments.filter(comment=comment, file_name="note.txt").exists())

    def test_employee_can_post_file_only_comment(self):
        ticket = EmployeeTicket.objects.create(
            employee=self.employee,
            title="File only",
            description="",
            created_by=self.admin,
        )

        self.client.force_authenticate(user=self.emp_user)
        uploaded = self.client.post(
            f"/api/employee-tickets/{ticket.id}/comments/",
            data={
                "ticket": str(ticket.id),
                "files": [SimpleUploadedFile("screenshot.png", b"image bytes", content_type="image/png")],
            },
            format="multipart",
        )
        self.assertEqual(uploaded.status_code, 201)
        body = uploaded.json()
        self.assertEqual(body.get("text"), "")
        self.assertTrue(body.get("attachments"))
        comment = ticket.comments.get()
        self.assertTrue(ticket.attachments.filter(comment=comment, file_name="screenshot.png").exists())

    def test_admin_can_assign_and_unassign_via_patch(self):
        other_user = User.objects.create_user(
            username="emp2_ticket",
            email="emp2_ticket@example.com",
            phoneno="9000000005",
            password="pass1234",
        )
        other_employee = EmployeeProfile.objects.create(
            user=other_user,
            employee_id="DI30002",
            phone="9000000005",
            designation="Dev",
            status="active",
        )

        ticket = EmployeeTicket.objects.create(
            employee=self.employee,
            title="Assign me",
            description="",
            created_by=self.admin,
        )

        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(
            f"/api/employee-tickets/{ticket.id}/",
            data={"assigned_to": other_employee.id, "reason": "Initial assignment"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)

        res2 = self.client.get(f"/api/employee-tickets/{ticket.id}/")
        self.assertEqual(res2.status_code, 200)
        body = res2.json()
        self.assertEqual(body.get("assigned_to", {}).get("id"), other_employee.id)
        self.assertTrue(bool(body.get("assigned_at")))
        self.assertTrue(len(body.get("assignment_history", [])) >= 1)

        res3 = self.client.patch(
            f"/api/employee-tickets/{ticket.id}/",
            data={"assigned_to": None, "reason": "Unassign"},
            format="json",
        )
        self.assertEqual(res3.status_code, 200)
        res4 = self.client.get(f"/api/employee-tickets/{ticket.id}/")
        self.assertEqual(res4.status_code, 200)
        self.assertIsNone(res4.json().get("assigned_to"))

    def test_ticket_detail_serializes_comment_author_and_assignee_compatibility(self):
        other_user = User.objects.create_user(
            username="emp2_ticket",
            email="emp2_ticket_2@example.com",
            phoneno="9000000006",
            password="pass1234",
        )
        other_employee = EmployeeProfile.objects.create(
            user=other_user,
            employee_id="DI30002",
            phone="9000000006",
            designation="QA",
            status="active",
        )

        ticket = EmployeeTicket.objects.create(
            employee=self.employee,
            title="Compat ticket",
            description="Needs compatibility",
            created_by=self.admin,
            assigned_to=other_employee,
        )

        self.client.force_authenticate(user=self.emp_user)
        res = self.client.post(
            f"/api/employee-tickets/{ticket.id}/comments/",
            data={"text": "I updated progress"},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual(body.get("author_name"), self.emp_user.username)
        self.assertEqual(body.get("author", {}).get("id"), self.emp_user.id)

        self.client.force_authenticate(user=self.admin)
        detail = self.client.get(f"/api/employee-tickets/{ticket.id}/")
        self.assertEqual(detail.status_code, 200)
        ticket_body = detail.json()
        self.assertEqual(ticket_body.get("assigned_to", {}).get("id"), other_employee.id)
        self.assertEqual(ticket_body.get("assigned_to_ids"), [other_employee.id])
        self.assertEqual(ticket_body.get("assignees", [{}])[0].get("id"), other_employee.id)

    def test_project_tickets_bridge_relationships_private_and_current_projects(self):
        """
        Verify:
        1. Project A -> Ticket A (PrivateProjectPlan -> PrivateProjectTicketAssignment -> EmployeeTicket)
        2. Project B -> Ticket B (PrivateProjectPlan -> PrivateProjectTicketAssignment -> EmployeeTicket)
        3. Project C -> Ticket C (CurrentProjectPlan -> CurrentProjectTicketAssignment -> EmployeeTicket)
        4. Opening Project A returns Ticket A with ticket_number, title, status, priority, assignees
        5. Ticket A must NOT appear under Project B
        6. Ticket B must NOT appear under Project A
        7. Project C returns Ticket C, and neither Ticket A nor Ticket B
        """
        self.client.force_authenticate(user=self.admin)

        # Create second employee
        other_user = User.objects.create_user(
            username="emp_b",
            email="emp_b@example.com",
            phoneno="9000000007",
            password="pass1234",
        )
        employee_b = EmployeeProfile.objects.create(
            user=other_user,
            employee_id="DI30003",
            phone="9000000007",
            designation="Dev",
            status="active",
        )

        # ---------------------------------------------------------
        # 1. Setup Project A (Private Project) & Employee A
        # ---------------------------------------------------------
        project_a = Project.objects.create(title="Project A", description="Desc A", status="in_progress")
        plan_a = PrivateProjectPlan.objects.create(project=project_a, project_name="Project A Plan")
        PrivateProjectAssignment.objects.create(plan=plan_a, employee=self.employee, status="assigned")

        # ---------------------------------------------------------
        # 2. Setup Project B (Private Project) & Employee B
        # ---------------------------------------------------------
        project_b = Project.objects.create(title="Project B", description="Desc B", status="in_progress")
        plan_b = PrivateProjectPlan.objects.create(project=project_b, project_name="Project B Plan")
        PrivateProjectAssignment.objects.create(plan=plan_b, employee=employee_b, status="assigned")

        # ---------------------------------------------------------
        # 3. Create Ticket A linked to Project A
        # ---------------------------------------------------------
        payload_a = {
            "employee": self.employee.id,
            "project_id": project_a.id,
            "title": "Ticket A - Database Migration",
            "description": "Perform migration on Project A",
            "priority": "high",
            "status": "pending",
            "assignee_ids": [self.employee.id],
        }
        res_a = self.client.post("/api/employee-tickets/", data=payload_a, format="json")
        self.assertEqual(res_a.status_code, 201)
        ticket_a_data = res_a.json()
        ticket_a_id = ticket_a_data.get("id")
        self.assertTrue(ticket_a_id)

        # Verify bridge table record was created for Project A
        self.assertTrue(
            PrivateProjectTicketAssignment.objects.filter(
                plan=plan_a,
                employee=self.employee,
                ticket_id=ticket_a_id,
            ).exists()
        )

        # ---------------------------------------------------------
        # 4. Create Ticket B linked to Project B
        # ---------------------------------------------------------
        payload_b = {
            "employee": employee_b.id,
            "project_id": project_b.id,
            "title": "Ticket B - API Integration",
            "description": "Integrate 3rd party API on Project B",
            "priority": "low",
            "status": "in_progress",
            "assignee_ids": [employee_b.id],
        }
        res_b = self.client.post("/api/employee-tickets/", data=payload_b, format="json")
        self.assertEqual(res_b.status_code, 201)
        ticket_b_data = res_b.json()
        ticket_b_id = ticket_b_data.get("id")
        self.assertTrue(ticket_b_id)

        # Verify bridge table record was created for Project B
        self.assertTrue(
            PrivateProjectTicketAssignment.objects.filter(
                plan=plan_b,
                employee=employee_b,
                ticket_id=ticket_b_id,
            ).exists()
        )

        # ---------------------------------------------------------
        # 5. Query Project A tickets via GET /api/private-projects/<id>/tickets/
        # ---------------------------------------------------------
        res_proj_a_tickets = self.client.get(f"/api/private-projects/{project_a.id}/tickets/")
        self.assertEqual(res_proj_a_tickets.status_code, 200)
        proj_a_tickets = res_proj_a_tickets.json()
        proj_a_ticket_ids = [t["id"] for t in proj_a_tickets]

        # Ticket A must appear under Project A
        self.assertIn(ticket_a_id, proj_a_ticket_ids)
        # Ticket B must NOT appear under Project A
        self.assertNotIn(ticket_b_id, proj_a_ticket_ids)

        # Verify fields on Ticket A
        ticket_a_item = next(t for t in proj_a_tickets if t["id"] == ticket_a_id)
        self.assertTrue(bool(ticket_a_item.get("ticket_number")))
        self.assertEqual(ticket_a_item.get("title"), "Ticket A - Database Migration")
        self.assertIn(ticket_a_item.get("status"), ["open", "pending"])
        self.assertEqual(ticket_a_item.get("priority"), "high")
        self.assertTrue(len(ticket_a_item.get("assignees", [])) >= 1)
        self.assertEqual(ticket_a_item["assignees"][0]["id"], self.employee.id)

        # ---------------------------------------------------------
        # 6. Query Project B tickets via GET /api/private-projects/<id>/tickets/
        # ---------------------------------------------------------
        res_proj_b_tickets = self.client.get(f"/api/private-projects/{project_b.id}/tickets/")
        self.assertEqual(res_proj_b_tickets.status_code, 200)
        proj_b_tickets = res_proj_b_tickets.json()
        proj_b_ticket_ids = [t["id"] for t in proj_b_tickets]

        # Ticket B must appear under Project B
        self.assertIn(ticket_b_id, proj_b_ticket_ids)
        # Ticket A must NOT appear under Project B!
        self.assertNotIn(ticket_a_id, proj_b_ticket_ids)

        # Verify fields on Ticket B
        ticket_b_item = next(t for t in proj_b_tickets if t["id"] == ticket_b_id)
        self.assertTrue(bool(ticket_b_item.get("ticket_number")))
        self.assertEqual(ticket_b_item.get("title"), "Ticket B - API Integration")
        self.assertEqual(ticket_b_item.get("status"), "in_progress")
        self.assertEqual(ticket_b_item.get("priority"), "low")
        self.assertTrue(len(ticket_b_item.get("assignees", [])) >= 1)
        self.assertEqual(ticket_b_item["assignees"][0]["id"], employee_b.id)

        # ---------------------------------------------------------
        # 7. Check Project Details API (GET /api/private-projects/<id>/)
        # ---------------------------------------------------------
        res_proj_a_detail = self.client.get(f"/api/private-projects/{project_a.id}/")
        self.assertEqual(res_proj_a_detail.status_code, 200)
        detail_a = res_proj_a_detail.json()
        detail_a_ticket_ids = [t["id"] for t in detail_a.get("tickets", [])]
        self.assertIn(ticket_a_id, detail_a_ticket_ids)
        self.assertNotIn(ticket_b_id, detail_a_ticket_ids)

        # ---------------------------------------------------------
        # 8. Setup Project C (Current Project flow)
        # ---------------------------------------------------------
        project_c = Project.objects.create(title="Project C", description="Desc C", status="in_progress")
        plan_c = CurrentProjectPlan.objects.create(project=project_c, project_name="Project C Plan")
        CurrentProjectAssignment.objects.create(plan=plan_c, employee=self.employee, status="assigned")

        payload_c = {
            "employee": self.employee.id,
            "project_id": project_c.id,
            "title": "Ticket C - Current Project Task",
            "description": "Task for Current Project C",
            "priority": "medium",
            "status": "pending",
            "assignee_ids": [self.employee.id],
        }
        res_c = self.client.post("/api/employee-tickets/", data=payload_c, format="json")
        self.assertEqual(res_c.status_code, 201)
        ticket_c_data = res_c.json()
        ticket_c_id = ticket_c_data.get("id")
        self.assertTrue(ticket_c_id)

        # Verify bridge table record was created for Project C in CurrentProjectTicketAssignment
        self.assertTrue(
            CurrentProjectTicketAssignment.objects.filter(
                plan=plan_c,
                employee=self.employee,
                ticket_id=ticket_c_id,
            ).exists()
        )

        # Query Project C tickets via GET /api/private-projects/<id>/tickets/
        res_proj_c_tickets = self.client.get(f"/api/private-projects/{project_c.id}/tickets/")
        self.assertEqual(res_proj_c_tickets.status_code, 200)
        proj_c_tickets = res_proj_c_tickets.json()
        proj_c_ticket_ids = [t["id"] for t in proj_c_tickets]

        # Ticket C must appear under Project C
        self.assertIn(ticket_c_id, proj_c_ticket_ids)
        # Tickets A and B must NOT appear under Project C
        self.assertNotIn(ticket_a_id, proj_c_ticket_ids)
        self.assertNotIn(ticket_b_id, proj_c_ticket_ids)

        # Query Project C tickets via GET /api/projects/<id>/tickets/
        res_proj_c_tickets2 = self.client.get(f"/api/projects/{project_c.id}/tickets/")
        self.assertEqual(res_proj_c_tickets2.status_code, 200)
        proj_c_tickets2 = res_proj_c_tickets2.json()
        proj_c_ticket_ids2 = [t["id"] for t in proj_c_tickets2]
        self.assertIn(ticket_c_id, proj_c_ticket_ids2)
        self.assertNotIn(ticket_a_id, proj_c_ticket_ids2)
        self.assertNotIn(ticket_b_id, proj_c_ticket_ids2)

    def test_employee_and_admin_comment_attachments(self):
        # 1. Create a ticket
        self.client.force_authenticate(user=self.admin)
        ticket = EmployeeTicket.objects.create(
            employee=self.employee,
            title="Ticket with Attachments",
            description="Testing attachments in comments",
            created_by=self.admin,
        )

        # 2. Admin posts comment with attachment via multipart/form-data
        admin_file = SimpleUploadedFile("admin_doc.txt", b"Admin report contents", content_type="text/plain")
        res_admin_comment = self.client.post(
            f"/api/employee-tickets/{ticket.id}/comments/",
            data={"text": "Admin comment with doc", "files": admin_file},
            format="multipart",
        )
        self.assertEqual(res_admin_comment.status_code, 201)
        admin_comment_data = res_admin_comment.json()
        self.assertEqual(admin_comment_data.get("text"), "Admin comment with doc")
        self.assertTrue(len(admin_comment_data.get("attachments", [])) == 1)
        att = admin_comment_data["attachments"][0]
        self.assertEqual(att.get("file_name"), "admin_doc.txt")
        self.assertTrue(bool(att.get("url") or att.get("file_url") or att.get("file")))

        # 3. Employee posts comment with attachment via multipart/form-data
        self.client.force_authenticate(user=self.emp_user)
        emp_file = SimpleUploadedFile("emp_screenshot.png", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR", content_type="image/png")
        res_emp_comment = self.client.post(
            f"/api/employee-tickets/{ticket.id}/comments/",
            data={"text": "Employee response with screenshot", "files": emp_file},
            format="multipart",
        )
        self.assertEqual(res_emp_comment.status_code, 201)
        emp_comment_data = res_emp_comment.json()
        self.assertEqual(emp_comment_data.get("text"), "Employee response with screenshot")
        self.assertTrue(len(emp_comment_data.get("attachments", [])) == 1)
        emp_att = emp_comment_data["attachments"][0]
        self.assertEqual(emp_att.get("file_name"), "emp_screenshot.png")
        self.assertTrue(bool(emp_att.get("url") or emp_att.get("file_url") or emp_att.get("file")))

        # 4. Employee fetches ticket details - both comments and their attachments must be present!
        res_detail_emp = self.client.get(f"/api/employee-tickets/{ticket.id}/")
        self.assertEqual(res_detail_emp.status_code, 200)
        detail_data = res_detail_emp.json()
        comments = detail_data.get("comments", [])
        self.assertEqual(len(comments), 2)
        # Note: EmployeeTicketComment model default ordering is ['-created_at'] (latest first)
        self.assertEqual(len(comments[0].get("attachments", [])), 1)
        self.assertEqual(comments[0]["attachments"][0]["file_name"], "emp_screenshot.png")
        self.assertEqual(len(comments[1].get("attachments", [])), 1)
        self.assertEqual(comments[1]["attachments"][0]["file_name"], "admin_doc.txt")

        # 5. Admin fetches comments list via /api/employee-tickets/<id>/comments/ (ordered by created_at ascending)
        self.client.force_authenticate(user=self.admin)
        res_comments_admin = self.client.get(f"/api/employee-tickets/{ticket.id}/comments/")
        self.assertEqual(res_comments_admin.status_code, 200)
        comments_list = res_comments_admin.json()
        self.assertEqual(len(comments_list), 2)
        self.assertEqual(comments_list[0]["attachments"][0]["file_name"], "admin_doc.txt")
        self.assertEqual(comments_list[1]["attachments"][0]["file_name"], "emp_screenshot.png")


