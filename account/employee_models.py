from django.db import models
from django.contrib.auth import get_user_model
import random
import string
from datetime import timedelta
from django.utils import timezone

User = get_user_model()


class EmployeeProfile(models.Model):
    """
    Employee profile model to store employee-specific information
    """
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('on_leave', 'On Leave'),
    ]
    EMPLOYMENT_TYPE_CHOICES = [
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('contract', 'Contract'),
        ('intern', 'Intern'),
        ('consultant', 'Consultant'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee_profile')
    employee_id = models.CharField(max_length=50, unique=True)  # e.g., DI10001
    phone = models.CharField(max_length=20)
    designation = models.CharField(max_length=100, blank=True)
    qualification = models.TextField(blank=True)
    employment_type = models.CharField(max_length=30, choices=EMPLOYMENT_TYPE_CHOICES, blank=True)
    location = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='inactive')
    private_project = models.ForeignKey('account.Project', on_delete=models.SET_NULL, null=True, blank=True, related_name='employees')
    linkedin_url = models.URLField(max_length=500, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        first = getattr(self.user, "firstname", "") or ""
        last = getattr(self.user, "lastname", "") or ""
        full = f"{first} {last}".strip()
        label = full or getattr(self.user, "username", "") or getattr(self.user, "email", "") or str(self.user_id)
        return f"{label} ({self.employee_id})"

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Employee Profile'
        verbose_name_plural = 'Employee Profiles'


class OTPVerification(models.Model):
    """
    Model to store OTP verification attempts and tokens
    """
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='otp_verifications')
    otp_code = models.CharField(max_length=6)  # 6-digit OTP
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=3)
    
    def is_expired(self):
        """Check if OTP has expired"""
        return timezone.now() > self.expires_at

    def is_valid(self):
        """Check if OTP is still valid for verification"""
        return not self.is_expired() and self.attempts < self.max_attempts and not self.is_verified

    def generate_otp(self):
        """Generate a random 6-digit OTP"""
        return ''.join(random.choices(string.digits, k=6))

    def __str__(self):
        return f"OTP for {self.employee.user.get_full_name()} - {self.created_at}"

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'OTP Verification'
        verbose_name_plural = 'OTP Verifications'


class LeaveRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='leave_requests')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class OvertimeRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ]

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='overtime_requests')
    date = models.DateField()
    hours = models.DecimalField(max_digits=5, decimal_places=2)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class EmployeeDocument(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    document_type = models.CharField(max_length=100, blank=True)
    file = models.FileField(upload_to='employee-documents/')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-uploaded_at']


class EmployeeTicket(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='tickets')
    ticket_number = models.CharField(max_length=32, unique=True, blank=True)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_employee_tickets')
    assigned_to = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_tickets')
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_employee_tickets')
    assigned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if (creating or not self.ticket_number) and self.pk and not self.ticket_number:
            year = timezone.now().year
            self.ticket_number = f"TCK-{year}-{int(self.pk):06d}"
            super().save(update_fields=["ticket_number"])

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=["ticket_number"]),
            models.Index(fields=["status", "priority", "created_at"]),
            models.Index(fields=["assigned_to", "created_at"]),
        ]


class EmployeeTicketAssignmentHistory(models.Model):
    ticket = models.ForeignKey(EmployeeTicket, on_delete=models.CASCADE, related_name='assignment_history')
    from_employee = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='ticket_assignment_from_events')
    to_employee = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='ticket_assignment_to_events')
    by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ticket_assignment_events')
    reason = models.TextField(blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-at']
        indexes = [
            models.Index(fields=["ticket", "at"]),
        ]


class EmployeeTicketAttachment(models.Model):
    ticket = models.ForeignKey(EmployeeTicket, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='employee-ticket-attachments/')
    file_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']


class EmployeeTicketComment(models.Model):
    ticket = models.ForeignKey(EmployeeTicket, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='employee_ticket_comments')
    author_employee = models.ForeignKey(EmployeeProfile, on_delete=models.SET_NULL, null=True, blank=True, related_name='ticket_comments')
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=["ticket", "created_at"]),
        ]


class PrivateProjectPlan(models.Model):
    project = models.OneToOneField('account.Project', on_delete=models.CASCADE, related_name='private_project_plan')
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    timeline = models.CharField(max_length=255, blank=True)
    project_name = models.CharField(max_length=255, blank=True)
    project_description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class PrivateProjectAssignment(models.Model):
    STATUS_CHOICES = [
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('review', 'Review'),
        ('completed', 'Completed'),
    ]

    plan = models.ForeignKey(PrivateProjectPlan, on_delete=models.CASCADE, related_name='assignments')
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='private_project_assignments')
    designation = models.CharField(max_length=120, blank=True, default="")
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    work = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='assigned')
    admin_comment = models.TextField(blank=True)
    employee_comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('plan', 'employee'),)
        ordering = ['employee_id', '-updated_at']


class PrivateProjectDailyUpdate(models.Model):
    assignment = models.ForeignKey(PrivateProjectAssignment, on_delete=models.CASCADE, related_name='daily_updates')
    date = models.DateField()
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']


class PrivateProjectTicketAssignment(models.Model):
    plan = models.ForeignKey(PrivateProjectPlan, on_delete=models.CASCADE, related_name='ticket_assignments')
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='private_project_ticket_assignments')
    ticket = models.ForeignKey(EmployeeTicket, on_delete=models.CASCADE, related_name='private_plan_assignments')
    assign_date = models.DateField(blank=True, null=True)
    expire_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('plan', 'employee', 'ticket'),)
        ordering = ['-updated_at']


class CurrentProjectPlan(models.Model):
    project = models.OneToOneField('account.Project', on_delete=models.CASCADE, related_name='current_project_plan')
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    timeline = models.CharField(max_length=255, blank=True)
    project_name = models.CharField(max_length=255, blank=True)
    project_description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']


class CurrentProjectAssignment(models.Model):
    STATUS_CHOICES = [
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('review', 'Review'),
        ('completed', 'Completed'),
    ]

    plan = models.ForeignKey(CurrentProjectPlan, on_delete=models.CASCADE, related_name='assignments')
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='current_project_assignments')
    designation = models.CharField(max_length=120, blank=True, default="")
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    work = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='assigned')
    admin_comment = models.TextField(blank=True)
    employee_comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('plan', 'employee'),)
        ordering = ['employee_id', '-updated_at']


class CurrentProjectDailyUpdate(models.Model):
    assignment = models.ForeignKey(CurrentProjectAssignment, on_delete=models.CASCADE, related_name='daily_updates')
    date = models.DateField()
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']


class CurrentProjectTicketAssignment(models.Model):
    plan = models.ForeignKey(CurrentProjectPlan, on_delete=models.CASCADE, related_name='ticket_assignments')
    employee = models.ForeignKey(EmployeeProfile, on_delete=models.CASCADE, related_name='current_project_ticket_assignments')
    ticket = models.ForeignKey(EmployeeTicket, on_delete=models.CASCADE, related_name='plan_assignments')
    assign_date = models.DateField(blank=True, null=True)
    expire_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (('plan', 'employee', 'ticket'),)
        ordering = ['-updated_at']
