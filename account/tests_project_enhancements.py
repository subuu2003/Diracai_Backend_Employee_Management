import json
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from account.models import Project
from account.employee_models import (
    EmployeeProfile,
    PrivateProjectPlan,
    PrivateProjectAssignment,
    PrivateProjectAttachment,
)

User = get_user_model()


class ProjectPlanEnhancementsTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Admin user
        self.admin = User.objects.create_user(
            username="admin_user_test",
            email="admin_user_test@example.com",
            phoneno="9000000081",
            password="pass1234",
        )
        self.admin.is_staff = True
        self.admin.save()

        # Assigned employee
        self.user_emp1 = User.objects.create_user(
            username="emp1_test",
            email="emp1_test@example.com",
            phoneno="9000000082",
            password="pass1234",
        )
        self.user_emp1.is_active = True
        self.user_emp1.save()
        self.emp1 = EmployeeProfile.objects.create(
            user=self.user_emp1,
            employee_id="DIR-881",
        )

        # Unassigned employee
        self.user_emp2 = User.objects.create_user(
            username="emp2_test",
            email="emp2_test@example.com",
            phoneno="9000000083",
            password="pass1234",
        )
        self.user_emp2.is_active = True
        self.user_emp2.save()
        self.emp2 = EmployeeProfile.objects.create(
            user=self.user_emp2,
            employee_id="DIR-882",
        )

        # Project and plan
        self.project = Project.objects.create(
            title="E-Pharmacy Platform",
            description="Initial work plan description",
            status="ongoing",
            completion_percentage=25,
        )
        self.plan = PrivateProjectPlan.objects.create(
            project=self.project,
            project_name=self.project.title,
            project_description=self.project.description,
        )

        # Assign emp1 to this project
        self.assignment = PrivateProjectAssignment.objects.create(
            plan=self.plan,
            employee=self.emp1,
            designation="Developer",
            status="in_progress",
        )
        self.emp1.private_project = self.project
        self.emp1.save()

    # -------------------------------------------------------------
    # 1. Attachment Title / Label Tests
    # -------------------------------------------------------------
    def test_attachment_upload_with_custom_title(self):
        self.client.force_authenticate(user=self.admin)
        f = SimpleUploadedFile("workflow_spec.docx", b"dummy content", content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        res = self.client.post(
            f"/api/private-projects/{self.project.id}/attachments/",
            data={"files": [f], "title": "Pharmacy Workflow Specification"},
            format="multipart",
        )
        self.assertEqual(res.status_code, 201)
        att = PrivateProjectAttachment.objects.filter(project=self.project).first()
        self.assertIsNotNone(att)
        self.assertEqual(att.title, "Pharmacy Workflow Specification")
        self.assertEqual(att.file_name, "workflow_spec.docx")

        # Serializer representation
        data = res.json()
        item = [x for x in data if x.get("file_name") == "workflow_spec.docx"][0]
        self.assertEqual(item.get("title"), "Pharmacy Workflow Specification")
        self.assertEqual(item.get("display_name"), "Pharmacy Workflow Specification")

    def test_attachment_upload_without_title_fallbacks_to_filename(self):
        self.client.force_authenticate(user=self.admin)
        f = SimpleUploadedFile("schema.pdf", b"%PDF-dummy", content_type="application/pdf")
        res = self.client.post(
            f"/api/private-projects/{self.project.id}/attachments/",
            data={"files": [f], "title": ""},
            format="multipart",
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        item = [x for x in data if x.get("file_name") == "schema.pdf"][0]
        self.assertEqual(item.get("title"), "")
        self.assertEqual(item.get("display_name"), "schema.pdf")

    def test_link_attachment_with_custom_title(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.post(
            f"/api/private-projects/{self.project.id}/attachments/",
            data={"link_url": "https://api-docs.example.com", "title": "API Documentation Portal"},
            format="multipart",
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        item = [x for x in data if x.get("link_url") == "https://api-docs.example.com"][0]
        self.assertEqual(item.get("title"), "API Documentation Portal")
        self.assertEqual(item.get("display_name"), "API Documentation Portal")

    # -------------------------------------------------------------
    # 2. Completion Percentage Tests (0-100, Independent of Status)
    # -------------------------------------------------------------
    def test_completion_percentage_saved_and_retrieved(self):
        self.client.force_authenticate(user=self.admin)
        res = self.client.patch(
            f"/api/private-projects/{self.project.id}/",
            data=json.dumps({"completion_percentage": 65}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.completion_percentage, 65)
        self.assertEqual(self.project.status, "ongoing")  # Status unchanged

    def test_changing_status_does_not_change_completion_percentage(self):
        self.client.force_authenticate(user=self.admin)
        # Explicitly set completion_percentage to 75
        self.project.completion_percentage = 75
        self.project.save()

        # Update status to completed without passing completion_percentage
        res = self.client.patch(
            f"/api/private-projects/{self.project.id}/",
            data=json.dumps({"status": "completed"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.project.refresh_from_db()
        self.assertEqual(self.project.status, "completed")
        self.assertEqual(self.project.completion_percentage, 75)  # Percentage preserved

    def test_completion_percentage_validation_rejects_out_of_bounds(self):
        self.client.force_authenticate(user=self.admin)
        res_negative = self.client.patch(
            f"/api/private-projects/{self.project.id}/",
            data=json.dumps({"completion_percentage": -10}),
            content_type="application/json",
        )
        self.assertEqual(res_negative.status_code, 400)

        res_over = self.client.patch(
            f"/api/private-projects/{self.project.id}/",
            data=json.dumps({"completion_percentage": 150}),
            content_type="application/json",
        )
        self.assertEqual(res_over.status_code, 400)

    # -------------------------------------------------------------
    # 3. Work Plan Rich Text Editor Permissions Tests
    # -------------------------------------------------------------
    def test_admin_can_update_work_plan(self):
        self.client.force_authenticate(user=self.admin)
        markdown_text = "### Implementation Scope\n\n- [x] Phase 1: DB Schema\n- [ ] Phase 2: APIs\n\n```python\nprint('hello')\n```"
        res = self.client.patch(
            f"/api/private-projects/{self.project.id}/",
            data=json.dumps({"project_description": markdown_text}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.project_description, markdown_text)

    def test_assigned_employee_can_update_work_plan(self):
        self.client.force_authenticate(user=self.user_emp1)
        markdown_text = "## Employee Updated Plan\n\n- Task A done\n- Task B in review"
        res = self.client.patch(
            f"/api/private-projects/{self.project.id}/",
            data=json.dumps({"project_description": markdown_text}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.project_description, markdown_text)

    def test_unassigned_employee_cannot_update_work_plan(self):
        self.client.force_authenticate(user=self.user_emp2)
        res = self.client.patch(
            f"/api/private-projects/{self.project.id}/",
            data=json.dumps({"project_description": "Unauthorized hack"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 403)

    def test_unauthenticated_cannot_update_work_plan(self):
        self.client.logout()
        res = self.client.patch(
            f"/api/private-projects/{self.project.id}/",
            data=json.dumps({"project_description": "Anonymous"}),
            content_type="application/json",
        )
        self.assertIn(res.status_code, [401, 403])
